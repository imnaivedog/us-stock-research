# runbook

# Runbook · daily/cron 操作 + 回滚预案

> 用户在 LightOS terminal 跑这些 · codex 不直接 ssh
> 

## 1. 手动跑 daily ETL

```bash
cd ~/us-stock-research
set -a && source .env && set +a   # V5+1 P1 后理论不需要

# 正常入口
uv run --package usstock-data usstock-data daily

# 指定日期重跑（幂等 UPSERT）
uv run --package usstock-data usstock-data daily --as-of 2026-04-29
```

## 2. universe sync

```bash
uv run --package usstock-data usstock-data universe sync
# 期望输出（cutover 当前）：
# {"m": {"candidates": 1784, "upserted": 1784, "removed": 375}, "a": {"synced": 0}}
```

用户填 a_pool.yaml 5 thesis 后 · 期望 `a.synced ≥ 5`。

## 3. 看日志

```bash
# 今日 daily
tail -f ~/logs/daily-$(date +%F).log

# 找 ERROR
grep ERROR ~/logs/daily-$(date +%F).log

# 全周
ls -lt ~/logs/ | head
```

## 4. alert_log 诊断

```sql
-- 最近 2 小时所有 alert
SELECT created_at, severity, job_name, symbol, message
FROM alert_log
WHERE created_at > now() - interval '2 hours'
ORDER BY created_at DESC LIMIT 100;

-- ERROR 最多的 job
SELECT job_name, COUNT(*) AS n
FROM alert_log
WHERE severity='ERROR' AND created_at::date = current_date
GROUP BY job_name ORDER BY n DESC;
```

## 5. 4 表行数诊断（cutover 验证用）

```sql
SELECT 'quotes_daily' AS t, COUNT(*) AS n FROM quotes_daily WHERE trade_date = '2026-04-29'
UNION ALL SELECT 'macro_daily',          COUNT(*) FROM macro_daily          WHERE trade_date = '2026-04-29'
UNION ALL SELECT 'daily_indicators',     COUNT(*) FROM daily_indicators     WHERE trade_date = '2026-04-29'
UNION ALL SELECT 'symbol_universe(active)', COUNT(*) FROM symbol_universe   WHERE is_active = true;
```

## 6. 手动 backup

```bash
bash ~/scripts/weekly_backup.sh
# 产出: /lzcapp/document/usstock-backups/usstock-YYYY-MM-DD.sql.gz
ls -lh /lzcapp/document/usstock-backups/ | tail
```

## 7. 安装 / 更新 cron

```bash
# 拷贝最新 deploy/*.sh 到 ~/scripts/
cp ~/us-stock-research/deploy/daily.sh ~/scripts/
cp ~/us-stock-research/deploy/weekly_backup.sh ~/scripts/
chmod +x ~/scripts/*.sh

# 检查 / 编辑 cron
crontab -l
crontab -e

# 重启 cron service（如需）
sudo systemctl restart cron 2>/dev/null || sudo service cron restart
```

## 8. 回滚预案

### 8.1 数据回滚（最严重）

```bash
# 1. 找最近 backup
ls -lh /lzcapp/document/usstock-backups/

# 2. 解压 + restore
cd /tmp
gunzip -k /lzcapp/document/usstock-backups/usstock-YYYY-MM-DD.sql.gz
PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -d "$POSTGRES_DB" < /tmp/usstock-YYYY-MM-DD.sql
```

### 8.2 代码回滚

```bash
cd ~/us-stock-research
git log --oneline -10
git revert <bad-commit>           # 优先 revert · 保历史
# 或 git reset --hard <safe-commit> · 仅本地 · 不要 push --force
uv sync
```

### 8.3 .env 还原

用户保管 .env 备份（USER_OWNED §1）· 直接覆盖 `~/us-stock-research/.env` + `chmod 600`

## 9. 常用 SQL 速查

```sql
-- 最新交易日
SELECT MAX(trade_date) FROM quotes_daily;

-- 单股最近 20 日行情
SELECT trade_date, close, volume FROM quotes_daily WHERE symbol='NVDA' ORDER BY trade_date DESC LIMIT 20;

-- a 池当前清单
SELECT symbol, is_active, thesis_added_at FROM symbol_universe WHERE pool='a' ORDER BY thesis_added_at;

-- m 池规模
SELECT COUNT(*) FROM symbol_universe WHERE pool='m' AND is_active=true;

-- 主题动量榜（当日）
SELECT theme_id, momentum_score, quintile, rank FROM themes_score_daily
WHERE trade_date = (SELECT MAX(trade_date) FROM themes_score_daily)
ORDER BY rank LIMIT 10;
```

## 10. 紧急联络

- 用户在 chat 报错给 codex · 贴：日志 tail / alert_log 2h / 4 表行数三连结果
- 凭据问题用户自己处理（USER_OWNED §1）· codex 不要试图获取/重置