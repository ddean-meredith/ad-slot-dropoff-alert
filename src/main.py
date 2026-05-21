from __future__ import annotations

import argparse
import json
import logging
import logging.config
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from src.config import ConfigurationError, load_settings
from src.detector import detect_impression_drops
from src.gam_report import GamReportError, build_ad_manager_client, fetch_impression_snapshots
from src.storage import create_db_engine, ensure_schema, fetch_snapshots_for_date, upsert_daily_rows

logger = logging.getLogger(__name__)
PACIFIC_TZ = ZoneInfo('America/Los_Angeles')


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    load_dotenv()
    args = parse_args(argv)

    try:
        settings = load_settings()
        current_date, prior_date = resolve_report_dates(
            current_date_arg=args.current_date,
            prior_date_arg=args.prior_date,
        )
        logger.info('Running impression drop detection for %s vs %s', current_date, prior_date)

        engine = create_db_engine(settings.database_url)
        ensure_schema(engine)

        client = build_ad_manager_client(settings)
        snapshots = fetch_impression_snapshots(
            client=client,
            start_date=prior_date,
            end_date=current_date,
        )
        upsert_daily_rows(engine, snapshots)

        prior_rows = fetch_snapshots_for_date(engine, prior_date)
        current_rows = fetch_snapshots_for_date(engine, current_date)
        alerts = detect_impression_drops(
            prior_rows,
            current_rows,
            min_baseline_impressions=settings.min_baseline_impressions,
            drop_threshold_pct=settings.drop_threshold_pct,
            prior_date=prior_date,
            current_date=current_date,
        )

        print(json.dumps(alerts, indent=2))
        return 0
    except (ConfigurationError, GamReportError, ValueError) as exc:
        logger.error('%s', exc)
    except Exception:
        logger.exception('Unexpected failure while running the pipeline.')
    return 1


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Detect Google Ad Manager ad slot impression drops greater than a threshold.'
    )
    parser.add_argument(
        '--current-date',
        help='Current date to compare in YYYY-MM-DD format. Defaults to yesterday in America/Los_Angeles.',
    )
    parser.add_argument(
        '--prior-date',
        help='Prior date to compare in YYYY-MM-DD format. Defaults to the day before current-date.',
    )
    return parser.parse_args(argv)


def resolve_report_dates(
    *,
    current_date_arg: str | None,
    prior_date_arg: str | None,
) -> tuple[date, date]:
    current_date = _parse_cli_date(current_date_arg) if current_date_arg else default_current_date()
    prior_date = _parse_cli_date(prior_date_arg) if prior_date_arg else current_date - timedelta(days=1)

    if prior_date >= current_date:
        raise ValueError('prior_date must be earlier than current_date')

    return current_date, prior_date


def default_current_date(now: datetime | None = None) -> date:
    current_time = now or datetime.now(PACIFIC_TZ)
    return current_time.date() - timedelta(days=1)


def _parse_cli_date(raw_value: str) -> date:
    try:
        return date.fromisoformat(raw_value)
    except ValueError as exc:
        raise ValueError(f'Invalid date {raw_value!r}. Expected YYYY-MM-DD.') from exc


def configure_logging() -> None:
    config_path = Path(__file__).resolve().parents[1] / 'config' / 'logging.json'
    if config_path.exists():
        logging.config.dictConfig(json.loads(config_path.read_text()))
    else:
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s %(levelname)s [%(name)s] %(message)s',
        )


if __name__ == '__main__':
    sys.exit(main())
