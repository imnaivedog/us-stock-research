# Runbook

LightOS 运维参考。用户执行这些命令；Codex 不 SSH。

## Runtime

- OS：LightOS。
- User：`naivedog`。
- Repo：`~/us-stock-research/`。
- Python / venv：uv 管理的 `.venv/`。
- Postgres：17，`localhost:5432`，database `usstock`。
- Logs：`~/logs/`。
- Backups：`/lzcapp/document/usstock-backups/`。
- 系统时区：UTC。用户展示通常用 Asia/Shanghai。
- `.env`：repo root，权限 600，用户保管。

Codex 只能引用这些环境变量名，不能接触实际值：`DATABASE_URL`、`POSTGRES_HOST`、`POSTGRES_PORT`、`POSTGRES_DB`、`POSTGRES_USER`、`POSTGRES_PASSWORD`、`FMP_API_KEY`、`FRED_API_KEY`、`POLYGON_API_KEY`、`NOTION_TOKEN`、`NOTION_DAILY_DB_ID`、`DISCORD_WEBHOOK_URL`、`LOG_LEVEL`、`PYTHONUNBUFFERED`。

## 手动 daily

```bash
cd ~/us-stock-research

# normal
uv run --package usstock-data usstock-data daily

# idempotent rerun for a date
uv run --package usstock-data usstock-data daily --as-of 2026-04-29
uv run --package usstock-analytics usstock-analytics themes-score --date 2026-04-29
uv run --package usstock-analytics usstock-analytics signals --date 2026-04-29
uv run --package usstock-reports usstock-reports daily --date 2026-04-29 --no-discord
```

## universe sync

```bash
uv run --package usstock-data usstock-data universe sync
```

cutover 预期：M 池约 1784 active，用户填写 `config/a_pool.yaml` 前 A 池为 0。

## 日志

```bash
tail -f ~/logs/daily-$(date +%F).log
grep ERROR ~/logs/daily-$(date +%F).log
ls -lt ~/logs/ | head
```

## alert 排障

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

## 行数排障

```sql
SELECT 'quotes_daily' AS t, COUNT(*) AS n FROM quotes_daily WHERE trade_date = '2026-04-29'
UNION ALL SELECT 'macro_daily', COUNT(*) FROM macro_daily WHERE trade_date = '2026-04-29'
UNION ALL SELECT 'daily_indicators', COUNT(*) FROM daily_indicators WHERE trade_date = '2026-04-29'
UNION ALL SELECT 'symbol_universe(active)', COUNT(*) FROM symbol_universe WHERE is_active = true
UNION ALL SELECT 'themes_score_daily', COUNT(*) FROM themes_score_daily WHERE trade_date = '2026-04-29';
```

## cron

UTC：

```cron
30 22 * * 1-5 /home/naivedog/scripts/daily.sh >> /home/naivedog/logs/daily-$(date +\%F).log 2>&1
0 20 * * 6 /home/naivedog/scripts/weekly_backup.sh >> /home/naivedog/logs/backup-$(date +\%F).log 2>&1
```

Asia/Shanghai 等价：

```text
daily: Tue-Sat 06:30
backup: Sun 04:00
```

安装或更新 scripts：

```bash
cp ~/us-stock-research/deploy/daily.sh ~/scripts/
cp ~/us-stock-research/deploy/weekly_backup.sh ~/scripts/
chmod +x ~/scripts/*.sh
crontab -l
crontab -e
```

## backup

```bash
bash ~/scripts/weekly_backup.sh
ls -lh /lzcapp/document/usstock-backups/ | tail
```

## rollback

代码优先用 revert，不改写历史：

```bash
cd ~/us-stock-research
git log --oneline -10
git revert <bad-commit>
uv sync
```

数据库 restore 是严重操作，属于用户保留事项：

```bash
cd /tmp
gunzip -k /lzcapp/document/usstock-backups/usstock-YYYY-MM-DD.sql.gz
PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -d "$POSTGRES_DB" < /tmp/usstock-YYYY-MM-DD.sql
```

不要让 Codex 重置 secrets。`.env` restore 由用户处理。

## 常用 SQL

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

## 向 Codex 报 incident 时贴这些

- 跑过的 command 和 exit code。
- 最后 50 行 log。
- alert 排障 query。
- 行数排障 query。

不要贴 secrets。
