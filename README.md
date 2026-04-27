# US Stock Research M1 Bootstrap

Local M1 bootstrap for the V4 US stock swing-trading data system.

This repository only implements ADR-026 M1: one-shot local historical bootstrap. It does not implement signal logic, Cloud Run, Scheduler, Notion publishing, backtesting, BigQuery, DuckDB, real-time quotes, or the reserved GCS `cold/` prefix.

## Prereqs

- Python 3.11+
- `uv`
- A Financial Modeling Prep API key
- A Notion integration token with read access to the ETF audit database
- `gcloud` authenticated for project `naive-usstock-live`
- Cloud SQL Auth Proxy installed from the official Google guide: <https://cloud.google.com/sql/docs/postgres/connect-auth-proxy>
- GCP resources already created by the user:
  - Cloud SQL Postgres 15 instance `naive-usstock-live:us-central1:naive-usstock-db`
  - GCS bucket `gs://naive-usstock-data`

## First-Time Setup

```powershell
uv sync
Copy-Item .env.example .env
```

Fill these values in `.env`:

```dotenv
FMP_API_KEY=
NOTION_TOKEN=
NOTION_ETF_AUDIT_DB_ID=
POSTGRES_PASSWORD=
```

Start Cloud SQL Auth Proxy in a separate terminal:

```powershell
cloud-sql-proxy naive-usstock-live:us-central1:naive-usstock-db --port 5432
```

Apply the schema:

```powershell
psql "host=127.0.0.1 port=5432 dbname=usstock user=postgres password=<POSTGRES_PASSWORD>" -f db/schema.sql
```

Export the ETF audit seed from Notion:

```powershell
uv run python scripts/export_etf_audit.py
```

## Environment

Runtime values are pinned in `.env.example`:

- `GCP_PROJECT_ID=naive-usstock-live`
- `GCP_REGION=us-central1`
- `CLOUD_SQL_INSTANCE_CONNECTION_NAME=naive-usstock-live:us-central1:naive-usstock-db`
- `POSTGRES_HOST=127.0.0.1`
- `POSTGRES_PORT=5432`
- `POSTGRES_DB=usstock`
- `POSTGRES_USER=postgres`
- `USE_CLOUD_SQL_PROXY=true`
- `GCS_BOOTSTRAP_BUCKET=naive-usstock-data`
- `GCS_BOOTSTRAP_PREFIX=bootstrap/`

## Running M1

Fresh one-shot bootstrap:

```powershell
uv run python scripts/bootstrap_history.py --fresh
```

Resume after interruption:

```powershell
uv run python scripts/bootstrap_history.py --resume
```

Override the historical start date:

```powershell
uv run python scripts/bootstrap_history.py --fresh --start-date 2021-04-24
```

Dry-run writes parquet locally and uploads to GCS, but skips DB writes:

```powershell
uv run python scripts/bootstrap_history.py --fresh --dry-run
```

Local parquet output lands under:

```text
data/snapshots/bootstrap_YYYY-MM-DD/
```

GCS upload target:

```text
gs://naive-usstock-data/bootstrap/YYYY-MM-DD/
```

## Verifying Results

```sql
SELECT count(*) FROM quotes_daily;
SELECT count(*) FROM macro_daily;
SELECT count(*) FROM symbol_universe WHERE is_active = true;
SELECT count(*) FROM etf_holdings_latest;
SELECT count(*) FROM sp500_members_daily;
```

Expected M1 acceptance ranges:

- `quotes_daily` above roughly 1,200,000 rows
- `macro_daily` above roughly 1,200 rows
- `symbol_universe WHERE is_active = true` above roughly 1,100 rows
- GCS contains one parquet per active symbol plus macro parquet files under `bootstrap/YYYY-MM-DD/`

Resume test:

1. Start `uv run python scripts/bootstrap_history.py --fresh`.
2. Press Ctrl-C during quote history.
3. Run `uv run python scripts/bootstrap_history.py --resume`.
4. Confirm completed symbols listed in `_checkpoint.json` are skipped.

## Troubleshooting

### FMP 429 or 503

Requests use async `httpx`, `asyncio.Semaphore(5)`, and tenacity exponential backoff up to 60 seconds. If 429s persist, rerun with `--resume` after the rate window cools down.

### FMP Missing Macro Symbols

Some Starter-tier macro symbols are flaky, especially `^VIX`, `^DXY`, and `BTCUSD`. Missing macro series are logged as warnings and left NULL in `macro_daily`; M1 continues. `CLUSD` falls back to `USO` for WTI.

### Auth

For Postgres connection failures, confirm Cloud SQL Auth Proxy is running on `127.0.0.1:5432` and `.env` contains the correct `POSTGRES_PASSWORD`.

For GCS failures, confirm:

```powershell
gcloud auth application-default login
gcloud config set project naive-usstock-live
```

For Notion export failures, confirm the integration has read access to the ETF audit database and `.env` contains `NOTION_ETF_AUDIT_DB_ID`.

### Schema

Re-apply schema safely with:

```powershell
psql "host=127.0.0.1 port=5432 dbname=usstock user=postgres password=<POSTGRES_PASSWORD>" -f db/schema.sql
```

The DDL uses `CREATE TABLE IF NOT EXISTS` and upsert-friendly primary keys.

## Universe Curation Workflow

M2-S1 adds a weekly universe curation job for `symbol_universe`. It runs every Monday at 09:00 Asia/Shanghai and keeps active membership aligned to:

```text
FMP /stable/stock-screener marketCapMoreThan=1000000000 and isActivelyTrading=true
UNION
watchlist symbols
```

The job records only membership flips in `symbol_universe_changes`. `first_seen` is set with `COALESCE(first_seen, CURRENT_DATE)` when a symbol enters and is never overwritten. `last_seen` is cleared when a symbol is active and set to `CURRENT_DATE` when it leaves. The current production schema uses `is_active`; no `track_code` column is added.

The FMP screener is constrained to US common-stock venues only: `isEtf=false`, `isFund=false`, `country=US`, and `exchangeShortName=NASDAQ,NYSE,AMEX`. The job also applies the same ETF/fund/country/exchange filters defensively to the returned rows.

Manual dry-run:

```powershell
$env:PYTHONPATH="src"
uv run python -m us_stock.jobs.curate_universe --dry-run
```

Manual write run:

```powershell
$env:PYTHONPATH="src"
uv run python -m us_stock.jobs.curate_universe
```

Apply the migration:

```powershell
psql "host=127.0.0.1 port=5432 dbname=usstock user=postgres password=<POSTGRES_PASSWORD>" -f sql/migrations/2026_04_27_add_universe_change_tracking.sql
```

Cloud Run and Scheduler specs are in:

```text
deploy/cloud_run_jobs.yaml
deploy/cloud_scheduler.yaml
```

Deploy syntax check examples:

```powershell
gcloud run jobs replace deploy/cloud_run_jobs.yaml --region us-central1 --dry-run
gcloud scheduler jobs describe curate-universe-weekly --location us-central1
```

Failure guards:

- FMP screener failure or fewer than 500 rows exits before touching tables.
- Final active count below 500 aborts the transaction.
- Cloud SQL connection attempts are retried three times.
- Job failures send a Discord alert when `DISCORD_WEBHOOK_URL` is provided.

Rollback:

```powershell
# Run the migrate:down block in sql/migrations/2026_04_27_add_universe_change_tracking.sql
```
