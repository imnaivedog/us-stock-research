# Runbook

LightOS operations reference. User runs these commands; Codex does not SSH.

## Runtime

- OS: LightOS.
- User: `naivedog`.
- Repo: `~/us-stock-research/`.
- Python/venv: uv-managed `.venv/`.
- Postgres: 17 on `localhost:5432`, database `usstock`.
- Logs: `~/logs/`.
- Backups: `/lzcapp/document/usstock-backups/`.
- System timezone: UTC. User-facing time usually Asia/Shanghai.
- `.env`: repo root, permission 600, user-owned.

Environment keys Codex may reference by name only: `DATABASE_URL`, `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `FMP_API_KEY`, `FRED_API_KEY`, `POLYGON_API_KEY`, `NOTION_TOKEN`, `NOTION_DAILY_DB_ID`, `DISCORD_WEBHOOK_URL`, `LOG_LEVEL`, `PYTHONUNBUFFERED`.

## Manual Daily

```bash
cd ~/us-stock-research

# normal
uv run --package usstock-data usstock-data daily

# idempotent rerun for a date
uv run --package usstock-data usstock-data daily --as-of 2026-04-29
uv run --package usstock-analytics usstock-analytics themes-score --date 2026-04-29
uv run --package usstock-analytics usstock-analytics signals --date 2026-04-29 --pool m
uv run --package usstock-reports usstock-reports daily --date 2026-04-29 --no-discord
```

## Universe Sync

```bash
uv run --package usstock-data usstock-data universe sync
```

Expected at cutover: M pool around 1784 active, A pool 0 until user fills `config/a_pool.yaml`.

## Logs

```bash
tail -f ~/logs/daily-$(date +%F).log
grep ERROR ~/logs/daily-$(date +%F).log
ls -lt ~/logs/ | head
```

## Alert Triage

```sql
SELECT created_at, severity, job_name, category, symbol, LEFT(message, 120) AS msg
FROM alert_log
WHERE created_at > now() - interval '2 hours'
ORDER BY created_at DESC
LIMIT 100;

SELECT job_name, severity, COUNT(*) AS n
FROM alert_log
WHERE created_at::date = current_date
GROUP BY job_name, severity
ORDER BY n DESC;
```

## Row Count Triage

```sql
SELECT 'quotes_daily' AS t, COUNT(*) AS n FROM quotes_daily WHERE trade_date = '2026-04-29'
UNION ALL SELECT 'macro_daily', COUNT(*) FROM macro_daily WHERE trade_date = '2026-04-29'
UNION ALL SELECT 'daily_indicators', COUNT(*) FROM daily_indicators WHERE trade_date = '2026-04-29'
UNION ALL SELECT 'symbol_universe(active)', COUNT(*) FROM symbol_universe WHERE is_active = true
UNION ALL SELECT 'themes_score_daily', COUNT(*) FROM themes_score_daily WHERE trade_date = '2026-04-29';
```

## Cron

UTC:

```cron
30 22 * * 1-5 /home/naivedog/scripts/daily.sh >> /home/naivedog/logs/daily-$(date +\%F).log 2>&1
0 20 * * 6 /home/naivedog/scripts/weekly_backup.sh >> /home/naivedog/logs/backup-$(date +\%F).log 2>&1
```

Asia/Shanghai equivalent:

```text
daily: 06:30 Tue-Sat
backup: 04:00 Sun
```

Install/update scripts:

```bash
cp ~/us-stock-research/deploy/daily.sh ~/scripts/
cp ~/us-stock-research/deploy/weekly_backup.sh ~/scripts/
chmod +x ~/scripts/*.sh
crontab -l
crontab -e
```

## Backup

```bash
bash ~/scripts/weekly_backup.sh
ls -lh /lzcapp/document/usstock-backups/ | tail
```

## Rollback

Prefer code revert over history rewriting:

```bash
cd ~/us-stock-research
git log --oneline -10
git revert <bad-commit>
uv sync
```

Database restore is severe and user-owned:

```bash
cd /tmp
gunzip -k /lzcapp/document/usstock-backups/usstock-YYYY-MM-DD.sql.gz
PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -d "$POSTGRES_DB" < /tmp/usstock-YYYY-MM-DD.sql
```

Never ask Codex to reset secrets. `.env` restore is user-owned.

## Useful SQL

```sql
SELECT MAX(trade_date) FROM quotes_daily;

SELECT trade_date, close, volume
FROM quotes_daily
WHERE symbol='NVDA'
ORDER BY trade_date DESC
LIMIT 20;

SELECT symbol, is_active, thesis_added_at
FROM symbol_universe
WHERE pool='a'
ORDER BY thesis_added_at;

SELECT COUNT(*)
FROM symbol_universe
WHERE pool='m' AND is_active=true;

SELECT theme_id, momentum_score, quintile, rank
FROM themes_score_daily
WHERE trade_date = (SELECT MAX(trade_date) FROM themes_score_daily)
ORDER BY rank
LIMIT 10;
```

## When Reporting An Incident To Codex

Paste:

- Command run and exit code.
- Last 50 log lines.
- Alert triage query.
- Row count triage query.

Do not paste secrets.
