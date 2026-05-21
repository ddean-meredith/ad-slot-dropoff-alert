from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy import BigInteger, Column, Date, DateTime, MetaData, String, Table
from sqlalchemy import UniqueConstraint, create_engine, delete, insert, select
from sqlalchemy.engine import Engine

from src.models import SnapshotRow

logger = logging.getLogger(__name__)

metadata = MetaData()

snapshot_table = Table(
    'ad_slot_impression_snapshots',
    metadata,
    Column('report_date', Date, nullable=False),
    Column('ad_slot', String(255), nullable=False),
    Column('full_ad_unit', String(1024), nullable=False),
    Column('impressions', BigInteger, nullable=False),
    Column('pulled_at', DateTime(timezone=True), nullable=False),
    UniqueConstraint('report_date', 'ad_slot', 'full_ad_unit', name='uq_snapshot_identity'),
)


def create_db_engine(database_url: str) -> Engine:
    _ensure_sqlite_directory(database_url)
    return create_engine(database_url, future=True)


def ensure_schema(engine: Engine) -> None:
    metadata.create_all(engine)


def upsert_daily_rows(engine: Engine, rows: Sequence[SnapshotRow]) -> int:
    if not rows:
        logger.info('No snapshot rows to store.')
        return 0

    prepared_rows = _deduplicate_rows(rows)
    affected_dates = sorted({row.report_date for row in prepared_rows})
    payload = [
        {
            'report_date': row.report_date,
            'ad_slot': row.ad_slot,
            'full_ad_unit': row.full_ad_unit,
            'impressions': row.impressions,
            'pulled_at': row.pulled_at or datetime.now(timezone.utc),
        }
        for row in prepared_rows
    ]

    with engine.begin() as connection:
        if affected_dates:
            connection.execute(
                delete(snapshot_table).where(snapshot_table.c.report_date.in_(affected_dates))
            )
        connection.execute(insert(snapshot_table), payload)

    logger.info('Stored %s snapshot row(s) for %s date(s).', len(payload), len(affected_dates))
    return len(payload)


def fetch_snapshots_for_date(engine: Engine, target_date: date) -> list[SnapshotRow]:
    query = (
        select(
            snapshot_table.c.report_date,
            snapshot_table.c.ad_slot,
            snapshot_table.c.full_ad_unit,
            snapshot_table.c.impressions,
            snapshot_table.c.pulled_at,
        )
        .where(snapshot_table.c.report_date == target_date)
        .order_by(snapshot_table.c.ad_slot, snapshot_table.c.full_ad_unit)
    )

    with engine.begin() as connection:
        rows = connection.execute(query).mappings().all()

    return [
        SnapshotRow(
            report_date=row['report_date'],
            ad_slot=row['ad_slot'],
            full_ad_unit=row['full_ad_unit'],
            impressions=int(row['impressions']),
            pulled_at=row['pulled_at'],
        )
        for row in rows
    ]


def _deduplicate_rows(rows: Iterable[SnapshotRow]) -> list[SnapshotRow]:
    deduplicated: dict[tuple[date, str, str], SnapshotRow] = {}
    for row in rows:
        deduplicated[(row.report_date, row.ad_slot, row.full_ad_unit)] = row
    return list(deduplicated.values())


def _ensure_sqlite_directory(database_url: str) -> None:
    sqlite_prefix = 'sqlite:///'
    if not database_url.startswith(sqlite_prefix):
        return

    db_path = database_url.removeprefix(sqlite_prefix)
    if db_path == ':memory:':
        return

    parent = Path(db_path).expanduser().resolve().parent
    parent.mkdir(parents=True, exist_ok=True)
