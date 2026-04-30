# M2-S1 Universe Curation

## commit chain

- `0232d8f` feat(db): add universe change tracking schema (ADR-029)
- `65c66a8` feat(jobs): implement curate_universe weekly job
- `50cd126` feat(deploy): wire curate-universe to Cloud Run + Scheduler

## 自查

### migration SQL 空 schema

Command：在临时 dev schema `codex_m2s1_emptycheck` 中执行 `db/schema.sql`，再执行 `sql/migrations/2026_04_27_add_universe_change_tracking.sql` 的 up block。

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

### migration SQL dev 幂等性

Command：在 dev `public` schema 上连续执行两次 migration up block。

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

### dry-run

Command: `$env:PYTHONPATH='src'; uv run python -m us_stock.jobs.curate_universe --dry-run --no-alert`

dev integration 前：

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

dev integration 后：

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

### pytest

Command：`uv run pytest`

```text
collected 9 items

tests\jobs\test_curate_universe.py ......                                [ 66%]
tests\test_etf_holdings_bad_weights.py ...                               [100%]

======================== 9 passed, 3 warnings in 1.17s ========================
```

### deploy YAML syntax

Command：本地用 PyYAML 解析两个 deploy specs。

```text
deploy/cloud_run_jobs.yaml: ok (dict)
deploy/cloud_scheduler.yaml: ok (dict)
```

已安装 SDK 的 command surface 不支持 `gcloud run jobs replace ... --dry-run`；命令返回 `unrecognized arguments: --dry-run`。未执行 production deployment。

## dev integration

Command: `$env:PYTHONPATH='src'; uv run python -m us_stock.jobs.curate_universe --no-alert`

执行前：

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

执行：

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

执行后：

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

audit sample：

```text
 symbol | change_date | change_type |     reason     | market_cap  
--------+-------------+-------------+----------------+-------------
 AAOI   | 2026-04-27  | added       | market_cap>=1B | 12194989396
 AAT    | 2026-04-27  | added       | market_cap>=1B |  1283683719
 AB     | 2026-04-27  | added       | market_cap>=1B |  4291058064
 ABTC   | 2026-04-27  | added       | market_cap>=1B |  1120016390
 ABXL   | 2026-04-27  | added       | market_cap>=1B |  2515182117
```

## 实施反馈

- 现有 schema 使用 `symbol_universe.is_active`，不是 `active`。因此保留现有列，并创建 `idx_su_active ON symbol_universe(is_active)`，没有新增 `active` 列。
- dev database 当时没有 `watchlist` 表。job 将缺失的 `watchlist` 视为空 watchlist 并记录 warning；本 PR 不新增 watchlist DDL。
- FMP stable screener 可返回数据的 endpoint 是 `/stable/company-screener`；`/stable/stock-screener` 在 dry-run 中失败。job 使用 `company-screener`，参数包括 `marketCapMoreThan`、`isActivelyTrading`、`isEtf=false`、`isFund=false`、`country=US`、`exchangeShortName=NASDAQ,NYSE,AMEX`、`limit=10000`。
- 初次 dev integration 未加 ETF/fund filters，返回 5680 行且包含 mutual funds。该运行已按要求用 2026-04-27 audit/delete SQL 回滚，然后用 filtered screener 重跑。
- Cloud Run/Scheduler YAML 已在本地解析。已安装的 `gcloud run jobs replace` 不支持 `--dry-run`，因此未执行任何 gcloud mutation command。
