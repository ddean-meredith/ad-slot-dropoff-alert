from __future__ import annotations

from collections.abc import Iterable
from datetime import date, timedelta

from src.models import SnapshotRow


def detect_impression_drops(
    prior_rows: Iterable[SnapshotRow],
    current_rows: Iterable[SnapshotRow],
    *,
    min_baseline_impressions: int,
    drop_threshold_pct: float,
    prior_date: date | None = None,
    current_date: date | None = None,
) -> list[dict[str, object]]:
    prior_map = _aggregate_by_slot(prior_rows)
    current_map = _aggregate_by_slot(current_rows)

    inferred_prior_date = prior_date or _infer_report_date(prior_map)
    inferred_current_date = current_date or _infer_report_date(current_map)
    if inferred_current_date is None and inferred_prior_date is not None:
        inferred_current_date = inferred_prior_date + timedelta(days=1)

    alerts: list[dict[str, object]] = []

    for key, (prior_impressions, prior_row) in prior_map.items():
        if prior_impressions <= 0 or prior_impressions < min_baseline_impressions:
            continue

        current_result = current_map.get(key)
        current_impressions = current_result[0] if current_result else 0
        absolute_drop = prior_impressions - current_impressions
        if absolute_drop <= 0:
            continue

        pct_decrease = (absolute_drop / prior_impressions) * 100
        if pct_decrease <= drop_threshold_pct:
            continue

        alert_current_date = (
            inferred_current_date
            or (current_result[1].report_date if current_result else prior_row.report_date + timedelta(days=1))
        )
        alert_prior_date = inferred_prior_date or prior_row.report_date

        alerts.append(
            {
                'ad_slot': prior_row.ad_slot,
                'full_ad_unit': prior_row.full_ad_unit,
                'prior_date': alert_prior_date.isoformat(),
                'current_date': alert_current_date.isoformat(),
                'prior_impressions': prior_impressions,
                'current_impressions': current_impressions,
                'absolute_drop': absolute_drop,
                'pct_decrease': round(pct_decrease, 2),
                'missing_current_row': current_result is None,
            }
        )

    alerts.sort(
        key=lambda alert: (
            -float(alert['pct_decrease']),
            -int(alert['absolute_drop']),
            str(alert['ad_slot']),
            str(alert['full_ad_unit']),
        )
    )
    return alerts


def _aggregate_by_slot(
    rows: Iterable[SnapshotRow],
) -> dict[tuple[str, str], tuple[int, SnapshotRow]]:
    aggregated: dict[tuple[str, str], tuple[int, SnapshotRow]] = {}
    for row in rows:
        key = (row.ad_slot, row.full_ad_unit)
        if key in aggregated:
            impressions, original_row = aggregated[key]
            aggregated[key] = (impressions + row.impressions, original_row)
        else:
            aggregated[key] = (row.impressions, row)
    return aggregated


def _infer_report_date(
    rows: dict[tuple[str, str], tuple[int, SnapshotRow]],
) -> date | None:
    for _key, (_impressions, row) in rows.items():
        return row.report_date
    return None
