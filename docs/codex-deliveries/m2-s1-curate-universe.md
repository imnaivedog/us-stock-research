# M2-S1 Curate Universe

## Commit Chain

- `0232d8f` feat(db): add universe change tracking schema (ADR-029)
- `65c66a8` feat(jobs): implement curate_universe weekly job
- `50cd126` feat(deploy): wire curate-universe to Cloud Run + Scheduler

## Self-Check

### Migration SQL Empty Schema

Command: run `db/schema.sql` plus `sql/migrations/2026_04_27_add_universe_change_tracking.sql` up block inside temporary dev schema `codex_m2s1_emptycheck`.

```text
DROP SCHEMA
CREATE SCHEMA
SET
CREATE TABLE
CREATE TABLE
CREATE TABLE
CREATE TABLE
CREATE TABLE
CREATE INDEX
CREATE INDEX
CREATE TABLE
CREATE INDEX
CREATE INDEX
BEGIN
ALTER TABLE
UPDATE 0
UPDATE 0
UPDATE 0
CREATE INDEX
CREATE INDEX
CREATE TABLE
CREATE INDEX
CREATE INDEX
COMMIT
DROP SCHEMA
```

### Migration SQL Dev Idempotency

Command: run migration up block twice against dev `public` schema.

```text
BEGIN
ALTER TABLE
UPDATE 1385
UPDATE 194
UPDATE 1385
CREATE INDEX
CREATE INDEX
CREATE TABLE
CREATE INDEX
CREATE INDEX
COMMIT
BEGIN
ALTER TABLE
UPDATE 1385
UPDATE 194
UPDATE 1385
CREATE INDEX
CREATE INDEX
CREATE TABLE
CREATE INDEX
CREATE INDEX
COMMIT
 active_after_migration 
------------------------
                   1385
(1 row)

 audit_rows_after_migration 
----------------------------
                          0
(1 row)
```

### Dry Run

Command: `$env:PYTHONPATH='src'; uv run python -m us_stock.jobs.curate_universe --dry-run --no-alert`

Before dev integration:

```text
[INFO] FMP screener returned 2067 symbols (market_cap >= 1B)
[INFO] Watchlist is empty; using market-cap rule only
[INFO] Should-be-active universe size: 2067
[INFO] Currently active: 1385
[INFO] Diff: +735 to_add (incl. 0 forced_in) / -53 to_remove / 1332 unchanged
[INFO] Creating 735 new symbols never seen before
[INFO] Dry-run: 735 added, 53 removed, 0 forced_in audit rows written
[INFO] Final active count: 2067
```

After dev integration:

```text
[INFO] FMP screener returned 2067 symbols (market_cap >= 1B)
[INFO] Watchlist is empty; using market-cap rule only
[INFO] Should-be-active universe size: 2067
[INFO] Currently active: 2067
[INFO] Diff: +0 to_add (incl. 0 forced_in) / -0 to_remove / 2067 unchanged
[INFO] Creating 0 new symbols never seen before
[INFO] Dry-run: 0 added, 0 removed, 0 forced_in audit rows written
[INFO] Final active count: 2067
```

### Pytest

Command: `uv run pytest`

```text
collected 9 items

tests\jobs\test_curate_universe.py ......                                [ 66%]
tests\test_etf_holdings_bad_weights.py ...                               [100%]

======================== 9 passed, 3 warnings in 1.17s ========================
```

### Deploy YAML Syntax

Command: local PyYAML parse for both deploy specs.

```text
deploy/cloud_run_jobs.yaml: ok (dict)
deploy/cloud_scheduler.yaml: ok (dict)
```

`gcloud run jobs replace ... --dry-run` was not available in installed SDK command surface; command returned `unrecognized arguments: --dry-run`. No production deployment was executed.

## Dev Integration

Command: `$env:PYTHONPATH='src'; uv run python -m us_stock.jobs.curate_universe --no-alert`

Before:

```text
 active_before_integration 
---------------------------
                      1385
(1 row)

 audit_before_integration 
--------------------------
                        0
(1 row)
```

Run:

```text
[INFO] FMP screener returned 2067 symbols (market_cap >= 1B)
[INFO] Watchlist is empty; using market-cap rule only
[INFO] Should-be-active universe size: 2067
[INFO] Currently active: 1385
[INFO] Diff: +735 to_add (incl. 0 forced_in) / -53 to_remove / 1332 unchanged
[INFO] Creating 735 new symbols never seen before
[INFO] Transaction committed: 735 added, 53 removed, 0 forced_in audit rows written
[INFO] Final active count: 2067
```

After:

```text
 active_after_integration 
--------------------------
                     2067
(1 row)

 audit_after_integration 
-------------------------
                     788
(1 row)
```

Audit sample:

```text
 symbol | change_date | change_type |     reason     | market_cap  
--------+-------------+-------------+----------------+-------------
 AAOI   | 2026-04-27  | added       | market_cap>=1B | 12194989396
 AAT    | 2026-04-27  | added       | market_cap>=1B |  1283683719
 AB     | 2026-04-27  | added       | market_cap>=1B |  4291058064
 ABTC   | 2026-04-27  | added       | market_cap>=1B |  1120016390
 ABXL   | 2026-04-27  | added       | market_cap>=1B |  2515182117
```

## 📦 实施反馈

- Existing schema uses `symbol_universe.is_active`, not `active`. I kept the existing column and created `idx_su_active ON symbol_universe(is_active)` instead of adding an `active` column.
- Dev database does not currently have a `watchlist` table. The job treats missing `watchlist` as an empty watchlist and logs a warning; no watchlist DDL is added to this PR.
- FMP stable screener endpoint that returned data was `/stable/company-screener`; `/stable/stock-screener` failed in dry-run. The job uses `company-screener` with `marketCapMoreThan`, `isActivelyTrading`, `isEtf=false`, `isFund=false`, `country=US`, `exchangeShortName=NASDAQ,NYSE,AMEX`, and `limit=10000`.
- Initial dev integration without ETF/fund filters returned 5680 rows and included mutual funds. That run was rolled back with the requested 2026-04-27 audit/delete SQL, then rerun with the filtered screener.
- Cloud Run/Scheduler YAML was parsed locally. The installed `gcloud run jobs replace` command did not support `--dry-run`, so no gcloud mutation command was run.
