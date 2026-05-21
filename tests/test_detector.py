from __future__ import annotations

from datetime import date

from src.detector import detect_impression_drops
from src.models import SnapshotRow


def snapshot(day: str, ad_slot: str, full_ad_unit: str, impressions: int) -> SnapshotRow:
    return SnapshotRow(
        report_date=date.fromisoformat(day),
        ad_slot=ad_slot,
        full_ad_unit=full_ad_unit,
        impressions=impressions,
    )


def test_normal_more_than_50_percent_drop_alerts() -> None:
    alerts = detect_impression_drops(
        prior_rows=[snapshot('2026-05-19', 'slot-a', '/sports/homepage/slot-a', 2000)],
        current_rows=[snapshot('2026-05-20', 'slot-a', '/sports/homepage/slot-a', 800)],
        min_baseline_impressions=1000,
        drop_threshold_pct=50,
        prior_date=date(2026, 5, 19),
        current_date=date(2026, 5, 20),
    )

    assert alerts == [
        {
            'ad_slot': 'slot-a',
            'full_ad_unit': '/sports/homepage/slot-a',
            'prior_date': '2026-05-19',
            'current_date': '2026-05-20',
            'prior_impressions': 2000,
            'current_impressions': 800,
            'absolute_drop': 1200,
            'pct_decrease': 60.0,
            'missing_current_row': False,
        }
    ]


def test_exactly_50_percent_drop_does_not_alert() -> None:
    alerts = detect_impression_drops(
        prior_rows=[snapshot('2026-05-19', 'slot-a', '/sports/homepage/slot-a', 2000)],
        current_rows=[snapshot('2026-05-20', 'slot-a', '/sports/homepage/slot-a', 1000)],
        min_baseline_impressions=1000,
        drop_threshold_pct=50,
        prior_date=date(2026, 5, 19),
        current_date=date(2026, 5, 20),
    )

    assert alerts == []


def test_below_threshold_does_not_alert() -> None:
    alerts = detect_impression_drops(
        prior_rows=[snapshot('2026-05-19', 'slot-a', '/sports/homepage/slot-a', 2000)],
        current_rows=[snapshot('2026-05-20', 'slot-a', '/sports/homepage/slot-a', 1200)],
        min_baseline_impressions=1000,
        drop_threshold_pct=50,
        prior_date=date(2026, 5, 19),
        current_date=date(2026, 5, 20),
    )

    assert alerts == []


def test_prior_impressions_below_baseline_does_not_alert() -> None:
    alerts = detect_impression_drops(
        prior_rows=[snapshot('2026-05-19', 'slot-a', '/sports/homepage/slot-a', 999)],
        current_rows=[snapshot('2026-05-20', 'slot-a', '/sports/homepage/slot-a', 0)],
        min_baseline_impressions=1000,
        drop_threshold_pct=50,
        prior_date=date(2026, 5, 19),
        current_date=date(2026, 5, 20),
    )

    assert alerts == []


def test_missing_current_day_row_alerts_and_marks_missing() -> None:
    alerts = detect_impression_drops(
        prior_rows=[snapshot('2026-05-19', 'slot-a', '/sports/homepage/slot-a', 3000)],
        current_rows=[],
        min_baseline_impressions=1000,
        drop_threshold_pct=50,
        prior_date=date(2026, 5, 19),
        current_date=date(2026, 5, 20),
    )

    assert alerts == [
        {
            'ad_slot': 'slot-a',
            'full_ad_unit': '/sports/homepage/slot-a',
            'prior_date': '2026-05-19',
            'current_date': '2026-05-20',
            'prior_impressions': 3000,
            'current_impressions': 0,
            'absolute_drop': 3000,
            'pct_decrease': 100.0,
            'missing_current_row': True,
        }
    ]


def test_prior_impressions_zero_does_not_alert() -> None:
    alerts = detect_impression_drops(
        prior_rows=[snapshot('2026-05-19', 'slot-a', '/sports/homepage/slot-a', 0)],
        current_rows=[snapshot('2026-05-20', 'slot-a', '/sports/homepage/slot-a', 0)],
        min_baseline_impressions=1000,
        drop_threshold_pct=50,
        prior_date=date(2026, 5, 19),
        current_date=date(2026, 5, 20),
    )

    assert alerts == []
