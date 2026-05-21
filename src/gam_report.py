        from __future__ import annotations

        import csv
        import gzip
        import io
        import logging
        import tempfile
        from collections.abc import Iterable
        from datetime import date, datetime, timezone
        from pathlib import Path

        from src.config import Settings
        from src.models import SnapshotRow

        logger = logging.getLogger(__name__)

        API_VERSION = 'v202602'

        DATE_HEADER_ALIASES = (
            'Dimension.DATE',
            'DATE',
            'Date',
        )

        AD_SLOT_HEADER_ALIASES = (
            # TODO: Validate whether AD_UNIT_CODE or another inventory identifier is the
            # best "ad slot" field in the real network's report output.
            'DimensionAttribute.AD_UNIT_CODE',
            'AD_UNIT_CODE',
            'Ad unit code',
            'Dimension.AD_UNIT_NAME',
            'AD_UNIT_NAME',
            'Ad unit',
        )

        FULL_AD_UNIT_HEADER_ALIASES = (
            # TODO: Confirm whether the selected report returns the full ad unit path or
            # only the leaf ad unit name. If it returns only the leaf name, enrich this
            # field from InventoryService using ad unit identifiers.
            'Dimension.AD_UNIT_NAME',
            'AD_UNIT_NAME',
            'Ad unit (all levels)',
            'Ad unit',
        )

        IMPRESSIONS_HEADER_ALIASES = (
            'Column.AD_SERVER_IMPRESSIONS',
            'AD_SERVER_IMPRESSIONS',
            'Ad server impressions',
        )


        class GamReportError(RuntimeError):
            """Raised when the Google Ad Manager adapter cannot complete a report run."""


        def build_ad_manager_client(settings: Settings):
            """Build an Ad Manager client from environment-backed settings."""
            try:
                from googleads import ad_manager
            except ImportError as exc:
                raise GamReportError(
                    'The googleads package is required. Install project dependencies first.'
                ) from exc

            config_yaml = '
'.join(
                [
                    'ad_manager:',
                    f'  application_name: {_yaml_quote(settings.gam_application_name)}',
                    f'  network_code: {_yaml_quote(settings.gam_network_code)}',
                    f'  client_id: {_yaml_quote(settings.gam_client_id)}',
                    f'  client_secret: {_yaml_quote(settings.gam_client_secret)}',
                    f'  refresh_token: {_yaml_quote(settings.gam_refresh_token)}',
                ]
            )

            try:
                return ad_manager.AdManagerClient.LoadFromString(config_yaml)
            except Exception as exc:  # pragma: no cover - depends on live GAM credentials
                raise GamReportError('Failed to initialize the Google Ad Manager client.') from exc


        def fetch_impression_snapshots(
            client,
            start_date: date,
            end_date: date,
        ) -> list[SnapshotRow]:
            """Run a GAM report and return parsed snapshot rows."""
            if end_date < start_date:
                raise ValueError('end_date must be on or after start_date')

            report_job = _build_report_job(start_date=start_date, end_date=end_date)
            report_path = Path(_download_report_to_tempfile(client=client, report_job=report_job))

            logger.info(
                'Downloaded GAM report for %s through %s to %s',
                start_date.isoformat(),
                end_date.isoformat(),
                report_path,
            )

            try:
                try:
                    with gzip.open(report_path, 'rt', encoding='utf-8-sig', newline='') as report_file:
                        rows = parse_csv_rows(report_file)
                except OSError:
                    with report_path.open('rt', encoding='utf-8-sig', newline='') as report_file:
                        rows = parse_csv_rows(report_file)
            finally:
                report_path.unlink(missing_ok=True)

            logger.info('Parsed %s snapshot row(s) from the GAM report.', len(rows))
            return rows


        def _build_report_job(start_date: date, end_date: date) -> dict[str, object]:
            # TODO: Confirm the exact dimension/attribute names in the target GAM network.
            # Some networks expose ad unit path columns with slightly different labels in CSV.
            report_query = {
                'dimensions': ['DATE', 'AD_UNIT_NAME'],
                'dimensionAttributes': ['AD_UNIT_CODE'],
                'columns': ['AD_SERVER_IMPRESSIONS'],
                'dateRangeType': 'CUSTOM_DATE',
                'startDate': start_date,
                'endDate': end_date,
            }
            return {'reportQuery': report_query}


        def _download_report_to_tempfile(client, report_job: dict[str, object]) -> str:
            try:
                from googleads import errors
            except ImportError as exc:
                raise GamReportError(
                    'The googleads package is required. Install project dependencies first.'
                ) from exc

            report_downloader = client.GetDataDownloader(version=API_VERSION)

            try:
                report_job_id = report_downloader.WaitForReport(report_job)
            except errors.AdManagerReportError as exc:  # pragma: no cover - live API only
                raise GamReportError('Google Ad Manager rejected the requested report.') from exc
            except Exception as exc:  # pragma: no cover - live API only
                raise GamReportError('Unexpected failure while running the GAM report.') from exc

            with tempfile.NamedTemporaryFile(suffix='.csv.gz', mode='wb', delete=False) as report_file:
                try:
                    report_downloader.DownloadReportToFile(report_job_id, 'CSV_DUMP', report_file)
                except Exception as exc:  # pragma: no cover - live API only
                    raise GamReportError('Failed to download the GAM report output.') from exc
                return report_file.name


        def parse_csv_rows(report_stream: io.TextIOBase | Iterable[str]) -> list[SnapshotRow]:
            reader = csv.DictReader(report_stream)
            if not reader.fieldnames:
                return []

            logger.debug('Parsing GAM CSV columns: %s', reader.fieldnames)
            parsed_rows: list[SnapshotRow] = []
            pulled_at = datetime.now(timezone.utc)

            for raw_row in reader:
                if not raw_row or _row_is_empty(raw_row):
                    continue

                report_date = _parse_report_date(_get_first_value(raw_row, DATE_HEADER_ALIASES))
                ad_slot = _clean_cell(_get_first_value(raw_row, AD_SLOT_HEADER_ALIASES, default=''))
                full_ad_unit = _clean_cell(
                    _get_first_value(raw_row, FULL_AD_UNIT_HEADER_ALIASES, default=ad_slot)
                )
                if not ad_slot:
                    ad_slot = full_ad_unit

                impressions = _parse_impressions(
                    _get_first_value(raw_row, IMPRESSIONS_HEADER_ALIASES, default='0')
                )

                parsed_rows.append(
                    SnapshotRow(
                        report_date=report_date,
                        ad_slot=ad_slot,
                        full_ad_unit=full_ad_unit or ad_slot,
                        impressions=impressions,
                        pulled_at=pulled_at,
                    )
                )

            return parsed_rows


        def _get_first_value(
            row: dict[str, str | None],
            candidate_headers: tuple[str, ...],
            default: str | None = None,
        ) -> str:
            for header in candidate_headers:
                if header in row and row[header] not in (None, ''):
                    return str(row[header])

            if default is not None:
                return default

            available = ', '.join(sorted(row))
            raise GamReportError(
                'Unable to find any expected CSV column in row. '
                f'Expected one of {candidate_headers!r}; available columns: {available}'
            )


        def _parse_report_date(raw_value: str) -> date:
            cleaned = _clean_cell(raw_value)
            for fmt in ('%Y-%m-%d', '%m/%d/%Y'):
                try:
                    return datetime.strptime(cleaned, fmt).date()
                except ValueError:
                    continue
            raise GamReportError(f'Unsupported report date value: {raw_value!r}')


        def _parse_impressions(raw_value: str) -> int:
            cleaned = _clean_cell(raw_value).replace(',', '')
            if cleaned == '':
                return 0

            try:
                return int(float(cleaned))
            except ValueError as exc:
                raise GamReportError(f'Unable to parse impressions value: {raw_value!r}') from exc


        def _clean_cell(value: str | None) -> str:
            if value is None:
                return ''
            return str(value).strip()


        def _row_is_empty(row: dict[str, str | None]) -> bool:
            return all(_clean_cell(value) == '' for value in row.values())


        def _yaml_quote(value: str) -> str:
            return "'" + value.replace("'", "''") + "'"
