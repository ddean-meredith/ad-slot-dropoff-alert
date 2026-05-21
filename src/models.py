from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True, slots=True)
class SnapshotRow:
    report_date: date
    ad_slot: str
    full_ad_unit: str
    impressions: int
    pulled_at: datetime | None = None
