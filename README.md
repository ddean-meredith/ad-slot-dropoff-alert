# ad-slot-dropoff-alert

MVP Python service that pulls Google Ad Manager impression data, stores daily ad slot snapshots, compares the latest day to the prior day, and prints alert rows as JSON for easy use from n8n.

## What this service does

- Authenticates to Google Ad Manager using the official `googleads` Python client library.
- Runs a report for a two-day window by default: yesterday and the day before, using the `America/Los_Angeles` timezone.
- Stores per-day snapshot rows in a relational database.
- Detects day-over-day impression drops greater than `DROP_THRESHOLD_PCT` when the prior day met `MIN_BASELINE_IMPRESSIONS`.
- Treats missing current-day rows as zero impressions and marks those alerts with `missing_current_row: true`.
- Prints alert rows as JSON to stdout so n8n can consume the result directly.

## Project structure

```text
.
├── .env.example
├── config/
│   └── logging.json
├── pyproject.toml
├── README.md
├── src/
│   ├── __init__.py
│   ├── config.py
│   ├── detector.py
│   ├── gam_report.py
│   ├── main.py
│   ├── models.py
│   └── storage.py
└── tests/
    └── test_detector.py
```

## Requirements

- Python 3.11+
- Google Ad Manager API credentials with report access
- A database reachable through `DATABASE_URL`

## Local setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev]"
cp .env.example .env
```

Fill in `.env` with real credentials and a real database URL before running the service.

## Environment variables

| Variable | Required | Default | Notes |
| --- | --- | --- | --- |
| `GAM_NETWORK_CODE` | Yes | - | Ad Manager network code. |
| `GAM_APPLICATION_NAME` | Yes | - | Sent as the application name in the GAM client. |
| `GAM_CLIENT_ID` | Yes | - | Google OAuth client ID. |
| `GAM_CLIENT_SECRET` | Yes | - | Google OAuth client secret. |
| `GAM_REFRESH_TOKEN` | Yes | - | Google OAuth refresh token for the GAM user. |
| `DATABASE_URL` | Yes | - | SQLAlchemy database URL, for example `sqlite:///data/ad_slot_dropoff.db` or a Postgres URL. |
| `MIN_BASELINE_IMPRESSIONS` | No | `1000` | Minimum prior-day impressions required before alerting. |
| `DROP_THRESHOLD_PCT` | No | `50` | Alert only when the percent decrease is strictly greater than this threshold. |

## Database table

The service creates this table automatically if it does not exist:

- `report_date`
- `ad_slot`
- `full_ad_unit`
- `impressions`
- `pulled_at`

Snapshot rows are stored in `ad_slot_impression_snapshots` with a uniqueness constraint on `(report_date, ad_slot, full_ad_unit)`.

## How to run manually

Default behavior compares yesterday vs the day before in `America/Los_Angeles`:

```bash
python -m src.main
```

Override the comparison dates explicitly:

```bash
python -m src.main --current-date 2026-05-20 --prior-date 2026-05-19
```

Logs are written to stderr. Alert JSON is written to stdout.

## Expected JSON output

Example output:

```json
[
  {
    "ad_slot": "top-banner",
    "full_ad_unit": "/network/homepage/top-banner",
    "prior_date": "2026-05-19",
    "current_date": "2026-05-20",
    "prior_impressions": 12345,
    "current_impressions": 4567,
    "absolute_drop": 7778,
    "pct_decrease": 63.0,
    "missing_current_row": false
  }
]
```

When a row exists on the prior day but is missing on the current day, the alert uses `current_impressions: 0` and sets `missing_current_row` to `true`.

## How n8n should call this script

A simple approach is to use an **Execute Command** node on a daily schedule.

Example command:

```bash
cd /path/to/repo && source .venv/bin/activate && python -m src.main
```

Notes for n8n:

- Provide the required environment variables to the node or to the worker environment.
- Consume stdout as JSON in the next node.
- Keep stderr for logs and troubleshooting.
- If you need a backfill or rerun for a specific day, pass `--current-date` and `--prior-date`.

## Detection rules

The detector alerts only when all of the following are true:

1. `prior_impressions >= MIN_BASELINE_IMPRESSIONS`
2. `current_impressions` are more than `DROP_THRESHOLD_PCT` lower than `prior_impressions`
3. The decrease is strictly greater than the threshold, so an exact 50 percent drop does not alert when the threshold is 50

## Testing

Run the unit tests with:

```bash
pytest
```

The current test suite focuses on the pure detector logic and covers:

- normal >50% drop
- exactly 50% drop
- below threshold
- prior impressions below baseline
- missing current-day row
- prior impressions zero

## GAM adapter assumptions

`src/gam_report.py` is intentionally isolated because Google Ad Manager report schemas can vary based on available dimensions and report compatibility.

Current assumptions:

- the report can be run with `DATE` and `AD_UNIT_NAME` dimensions
- the report can include `AD_UNIT_CODE` as a dimension attribute for the slot identifier
- the CSV contains `AD_SERVER_IMPRESSIONS`

There are explicit TODO comments in the adapter where the exact GAM dimension or column names may need to be adjusted after inspecting the real report output for your network.
