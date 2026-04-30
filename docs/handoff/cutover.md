# Cutover Handoff

Merged from the old 01/02/03/05 handoff files. This is the operational context for V5+1 and the remaining LightOS cutover.

## Current Context

Project: personal daily US stock research system with two pools:

- M pool: broad short-term momentum universe, roughly 1784 active symbols at cutover.
- A pool: user-owned long-thesis list, currently empty skeleton until the user fills `config/a_pool.yaml`.

Runtime:

- Production: LightOS, repo at `~/us-stock-research/`, Postgres 17 on `localhost:5432`, system timezone UTC.
- Codex workspace: Windows PowerShell at `D:\Dev\us-stock-research\`.
- Remote deployment is user-run. Codex does not SSH.

Cutover baseline:

- Git HEAD at handoff time: `4348cbc chore(deploy): readme troubleshooting + cron tz + alert_log category`.
- Backup: `/lzcapp/document/usstock-backups/usstock-cutover-2026-04-30.sql.gz` around 126MB.
- `.env` is at repo root on LightOS, permission 600, user-owned.
- A pool is expected to have 0 rows until the user fills thesis YAML.

## Known Issues For V5+1

| ID | Symptom | Root cause | V5+1 patch |
| --- | --- | --- | --- |
| P1 | Migrate fails with `fe_sendauth: no password supplied`. | CLI does not load repo `.env`. | Load `.env` in shared DB module. |
| P2 | `postgresql://` tries `psycopg2`. | SQLAlchemy defaults to v2 driver. | Normalize to `postgresql+psycopg://`. |
| P3 | `CREATE INDEX` fails on missing old-table columns such as `asset_class`. | DDL creates indexes before old tables receive `ALTER ADD COLUMN`. | Reorder DDL: create tables, alter columns, then indexes. |
| P4 | `corporate_actions` and `fundamentals` log huge `NoneType` ERROR streams. | FMP tier lacks endpoints; best-effort skip logs too loudly. | Demote expected skips to INFO/progress. |
| P5 | `.bak.*` files can enter commits. | Missing ignore rule. | Add `.gitignore` patterns. |
| P6 | V5+1 lacks changelog/retro. | Cutover work needs record. | Add changelog + change note. |

Out of scope for V5+1:

- Hermes MCP client-side integration.
- Holiday sentinel.
- GCP old-resource deletion.
- Secrets rotation.
- `master` -> `main` rename.
- Old Notion A pool DB deletion.

## First Diagnostic If Cutover Is Still Unclear

User runs this on LightOS:

```bash
cd ~/us-stock-research
echo "=== daily exit code: $? ==="

PG_URL="${DATABASE_URL/postgresql+psycopg:\/\//postgresql:\/\/}"
psql "$PG_URL" <<'SQL'
SELECT 'quotes_daily' AS tbl, COUNT(*) AS rows FROM quotes_daily WHERE trade_date='2026-04-29'
UNION ALL SELECT 'macro_daily', COUNT(*) FROM macro_daily WHERE trade_date='2026-04-29'
UNION ALL SELECT 'daily_indicators', COUNT(*) FROM daily_indicators WHERE trade_date='2026-04-29'
UNION ALL SELECT 'themes_members', COUNT(*) FROM themes_members
UNION ALL SELECT 'themes_master', COUNT(*) FROM themes_master
ORDER BY tbl;
SQL

psql "$PG_URL" -c "SELECT trade_date, severity, job_name, category, LEFT(message,80) AS msg FROM alert_log WHERE created_at > NOW() - INTERVAL '2 hours' ORDER BY id DESC LIMIT 20;"
```

Default path: even if diagnostics are noisy, finish V5+1 P1-P6 locally, push master, then ask the user to pull and rerun.

## After V5+1 Push

User-side sequence:

```bash
cd ~/us-stock-research
git pull origin master
uv sync

# P1/P2/P3 validation: should work without source .env and be idempotent.
uv run python -m usstock_data.schema.migrate
```

Rerun 2026-04-29:

```bash
cd ~/us-stock-research
DATE=2026-04-29

uv run --package usstock-data usstock-data daily --as-of $DATE
uv run --package usstock-analytics usstock-analytics themes-score --date $DATE
uv run --package usstock-analytics usstock-analytics a-pool signals --date $DATE
uv run --package usstock-analytics usstock-analytics signals --date $DATE --pool m
uv run --package usstock-reports usstock-reports daily --date $DATE --no-discord
```

Expected:

| Step | Expected result |
| --- | --- |
| Data daily | quotes around 1784, macro 1, indicators around 1784, corp/fund best-effort skip |
| themes-score | 31 `themes_score_daily` rows |
| a-pool signals | 0 rows while A pool YAML is empty |
| m-pool signals | some M signal rows depending on market state |
| reports | Notion daily row + page; no Discord when `--no-discord` |

## Cron Deployment

User copies deploy scripts:

```bash
cd ~/us-stock-research
cp deploy/daily.sh ~/scripts/daily.sh
cp deploy/weekly_backup.sh ~/scripts/weekly_backup.sh
chmod +x ~/scripts/*.sh
```

UTC cron:

```cron
30 22 * * 1-5 /home/naivedog/scripts/daily.sh
0 20 * * 6 /home/naivedog/scripts/weekly_backup.sh
```

Asia/Shanghai equivalent:

```cron
30 6 * * 2-6 /home/naivedog/scripts/daily.sh
0 4 * * 0 /home/naivedog/scripts/weekly_backup.sh
```

Keep system timezone UTC unless the user explicitly changes ops policy.

## Final Validation

```bash
DATE=2026-04-29
PG_URL="${DATABASE_URL/postgresql+psycopg:\/\//postgresql:\/\/}"

tail -50 ~/logs/daily-${DATE}.log 2>/dev/null || echo "(manual run may not have log)"

psql "$PG_URL" -c "SELECT trade_date, severity, job_name, category, LEFT(message,80) AS msg FROM alert_log WHERE trade_date='$DATE' ORDER BY id DESC;"

psql "$PG_URL" <<'SQL'
SELECT 'quotes_daily' AS tbl, COUNT(*) FROM quotes_daily WHERE trade_date='2026-04-29'
UNION ALL SELECT 'macro_daily', COUNT(*) FROM macro_daily WHERE trade_date='2026-04-29'
UNION ALL SELECT 'daily_indicators', COUNT(*) FROM daily_indicators WHERE trade_date='2026-04-29'
UNION ALL SELECT 'm_signals_daily', COUNT(*) FROM m_signals_daily WHERE trade_date='2026-04-29'
ORDER BY tbl;
SQL
```

Pass criteria:

- All five rerun steps exit 0.
- Alert noise is limited to known best-effort cases.
- quotes/indicators around active M pool size, macro exactly 1.
- Notion daily DB has a 2026-04-29 row and page.
- Discord is not sent during `--no-discord` validation.

## User-Owned Follow-Up

After cutover passes, the user may fill:

```yaml
- symbol: LITE
  status: watching
  added: 2026-04-29
  thesis_stop_mcap_b: <user-owned>
  target_mcap_b: <user-owned>
  thesis_summary: |
    AI data-center optical interconnect thesis.
  themes: [theme_ai_compute, theme_optical_module]
```

Repeat for COHR, MRVL, WDC, SNDK if desired. Thesis numbers and business text are user-owned.
