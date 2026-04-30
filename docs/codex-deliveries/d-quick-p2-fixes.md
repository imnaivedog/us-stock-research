# D-quick P2 修复记录

## 提交链(commit hash)

- `5290e0f` chore(env): document local bootstrap defaults
- `c8a3330` fix(macro): align macro_daily column names
- `211ff0b` fix(holdings): quarantine bad ETF weights

## P2.13 交付

- yaml 改动后完整内容:

```yaml
# FMP symbol codes used by the M1 macro loader.
vix: "^VIX"
spy: "SPY"
qqq: "QQQ"
tlt: "TLT"
gld: "GLD"
uup: "UUP"
hyg: "HYG"
lqd: "LQD"
dxy: "UDN"         # DXY proxy; ^DXY is 402 on Starter, UUP is already tracked above.
wti: "USO"         # WTI proxy; CLUSD is 402 on Starter.
btc: "BTCUSD"
ief: "IEF"         # 7-10y treasury ETF price sentiment; not a 10Y yield proxy.
us10y: "treasury_rates:year10"  # FMP treasury-rates 10Y yield.
us2y: "treasury_rates:year2"    # FMP treasury-rates 2Y yield; used for spread_10y_2y.
```

- migration 脚本路径: `migrations/20260427_p2_13_macro_daily_drop_close_suffix.sql`
- 加载代码 diff 关键几行:

```python
MACRO_SYMBOLS_PATH = PROJECT_ROOT / "config" / "macro_symbols.yaml"
MACRO_DB_COLUMNS = (
    "vix", "spy", "qqq", "tlt", "gld", "uup",
    "hyg", "lqd", "dxy", "wti", "btc", "ief",
)

for column in MACRO_DB_COLUMNS:
    row[column] = values.get(column)

macro_symbols = load_yaml(MACRO_SYMBOLS_PATH)
```

- 下游引用点改动清单:
  - `db/schema.sql`: `macro_daily` 列从 `spy_close`/`qqq_close`/`tlt_close`/`gld_close`/`uup_close`/`hyg_close`/`lqd_close`/`btc_close`/`ief_close` 改为无后缀列。
  - `scripts/bootstrap_history.py:35`: macro symbols 改读 `config/macro_symbols.yaml`。
  - `scripts/bootstrap_history.py:47`: macro DB 写入列集中在 `MACRO_DB_COLUMNS`。
  - `scripts/bootstrap_history.py:507`: macro row 构造不再映射到 `_close` 列。
  - `scripts/bootstrap_history.py:519`: `macro_daily` upsert `update_cols` 改为无后缀列。
  - `scripts/bootstrap_history.py:720`: 主流程加载独立 macro yaml。
- P2.12 顺手处理结果: FMP Starter 可访问 `/stable/treasury-rates`，所以 `us10y` 改为 `treasury_rates:year10`，删掉 IEI；`ief` 保留为 IEF ETF 价格情绪指标；`us2y` 改为 `treasury_rates:year2` 以保持 `spread_10y_2y` 为收益率差。

## P2.14 交付

- 校验函数位置: `scripts/bootstrap_history.py:194` 的 `bad_holding_weight_reason()`；调用点在 `scripts/bootstrap_history.py:538` 的 `process_all_etf_holdings()`。

```python
def bad_holding_weight_reason(weight: float | None) -> str | None:
    if weight is None or (isinstance(weight, float) and math.isnan(weight)):
        return "nan_weight"
    if weight <= 0:
        return "nonpositive_weight"
    if weight > HOLDING_WEIGHT_MAX:
        return "weight_overflow"
    return None
```

- 小批量实跑统计:
  - ETF: `IVV`, `IJH`, `IJR`, `QQQ`, `IPO`
  - 输入行数: `1702`
  - skip 行数: `6`
  - dry-run 可入主表行数: `1696`
  - Cloud SQL 写入: `0`，本次使用 `pg=None` + `dry_run=True`
- bad_rows.csv GCS 路径: `gs://naive-usstock-data/bad_rows/etf_holdings/2026-04-27.csv`
- bad_rows.csv 前 5 行示例:

```csv
symbol,asset,name,isin,securityCusip,sharesNumber,weightPercentage,marketValue,updatedAt,reason,loaded_at
IVV,,HOLOGIC INC,US436CVR0216,436CVR021,2843388.0,0.0,28433.88,2026-04-24 11:04:00,nonpositive_weight,2026-04-27T08:44:50.841668+00:00
IJH,,CASH COLLATERAL USD GSISW,US0669224778,066922477,350000.0,0.0,350000.0,2026-04-24 11:04:20,nonpositive_weight,2026-04-27T08:44:50.841668+00:00
IJR,,OMNIAB INC $12.50 VESTING Prvt,US68218J3014,68218J301,450637.0,0.0,4.51,2026-04-24 11:04:00,nonpositive_weight,2026-04-27T08:44:50.841668+00:00
IJR,,OMNIAB INC $15.00 VESTING Prvt,US68218J3014,68218J301,450637.0,0.0,4.51,2026-04-24 11:04:00,nonpositive_weight,2026-04-27T08:44:50.841668+00:00
QQQ,,CME E-Mini NASDAQ 100 Index Future,,CASHUSD00,1587830.23,0.0,0.0,2026-04-24 09:04:00,nonpositive_weight,2026-04-27T08:44:50.841668+00:00
```

- FMP weight 实际返回格式: `0-100`。小批量 parquet 中字段为 `weightPercentage`，5 个 loader ETF 的 sum 约为 `100`；follow-up 中 loader 将百分数字段归一到 0-1 后入主表，主表 quarantine 阈值为 `> 1.05`。

## P2.15 交付

- `.env.example` 完整内容:

```dotenv
PYTHONUNBUFFERED=1
FMP_API_KEY=

# Application Default Credentials
# Run: gcloud auth application-default login
GCP_PROJECT_ID=naive-usstock-live
GCP_REGION=us-central1
CLOUD_SQL_INSTANCE_CONNECTION_NAME=naive-usstock-live:us-central1:naive-usstock-db
USE_CLOUD_SQL_PROXY=true

POSTGRES_USER=postgres
POSTGRES_PASSWORD=
POSTGRES_DB=usstock
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5432

GCS_BOOTSTRAP_BUCKET=naive-usstock-data
GCS_BOOTSTRAP_PREFIX=bootstrap/
LOG_LEVEL=INFO
```

- 保留 / 删除变量说明:
  - 保留 `FMP_API_KEY`、Postgres、GCP、GCS 变量：M1 local bootstrap 仍直接使用。
  - 保留 `USE_CLOUD_SQL_PROXY`：`PostgresSettings` 仍接收该变量，且本地说明中仍以 proxy host/port 为默认连接形态。
  - 新增 `PYTHONUNBUFFERED=1` 与 `LOG_LEVEL=INFO`：分别对应容器/本地日志刷新与 `configure_logging()`。
  - 删除 `NOTION_TOKEN`、`NOTION_ETF_AUDIT_DB_ID`：P2.8/M2 之前 M1 不再导出 Notion。
  - 未添加 `GOOGLE_APPLICATION_CREDENTIALS`：按任务书使用 ADC 注释，不引导下载 SA key。
  - 新增 `Dockerfile`：使用 Python 3.11 slim + uv，默认命令为 local bootstrap dry-run。

## 六、Codex 自查清单(Codex 填)

- [x] migration 脚本在 dev 库跑过 forward；rollback 未在 dev 执行。
- [x] yaml + `macro_daily` schema + 加载代码 + 下游引用：macro 运行时代码和配置/schema 已无 `_close` 后缀；migration 文件保留旧列名用于 rename/rollback。
- [x] etf_holdings 加载小批量跑通 + bad_rows.csv 写到 GCS：输出 `{"db_rows": 1696, "input_rows": 1702, "skipped_rows": 6}`，上传日志进入 `uploaded ETF holdings bad rows` 分支。
- [ ] `cp .env.example .env`：仓库已有 `.env`，为避免覆盖本地 secrets 未执行复制；`uv sync` 通过；一行 smoke test 输出 `smoke ok`。
- [x] 所有 P2 改动 commit 独立，commit message 通过 `git commit -F` 写入。
- [x] 本任务书 scope 之外文件未修改；`.gitignore` 只新增 M1 遗留/坏行输出忽略项。

## 七、偏离记录(Codex 填)

- migration 本地 DB 执行未完成：本机有 `psql`/`initdb` 命令，但 `initdb -D data\tmp_pg_p213 -A trust -U postgres` 返回 `postgres.bki does not exist`；本机无 Docker；按任务要求未连接 Cloud SQL。
- `uv run ruff check .` 暴露多个既有 lint/格式项，分布在 `data/universe_filter.py`、`lib/fmp_client.py`、`lib/pg_client.py`、`scripts/backfill_quotes.py` 和 `scripts/bootstrap_history.py`。未扩大 scope 批量改格式；改为执行 `uv run ruff check scripts\bootstrap_history.py lib\gcs_client.py --select F,B,UP`，输出 `All checks passed!`。
- `.env.example` 未复制覆盖 `.env`，因为仓库根目录已经存在本地 `.env`，其中可能包含 secrets。

## PR #1 合并前 follow-up

- FMP treasury-rates probe:

```text
HTTP_STATUS:200
[
  {
    "date": "2024-01-05",
    "month1": 5.54,
    "month2": 5.48,
    "month3": 5.47,
    "month6": 5.24,
    "year1": 4.84,
```

- 路线: 方案 A。
- dev forward migration 后 `_close` 列查询:

```text
 column_name 
-------------
(0 rows)
```

- dev forward migration 后 `macro_daily` 列:

```text
  column_name  
---------------
 trade_date
 vix
 spy
 qqq
 tlt
 gld
 uup
 hyg
 lqd
 dxy
 wti
 btc
 ief
 spread_10y_2y
 created_at
 updated_at
 us10y
(17 rows)
```

- `uv run pytest`:

```text
collected 3 items

tests\test_etf_holdings_bad_weights.py ...                               [100%]

============================== 3 passed in 1.12s ==============================
```

- dev one-shot cleanup:

```text
 total_before 
--------------
        15141

 bad_before 
------------
       3288

DELETE 3288

 total_after 
-------------
       11853

 bad_after 
-----------
         0
```
