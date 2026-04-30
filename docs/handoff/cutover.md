# Cutover 交接

由旧 01/02/03/05 handoff 文件合并而来。本页保存 V5+1 和 LightOS 剩余 cutover 所需的操作上下文。

## 当前上下文

项目：个人日级美股研究系统，两个池：

- M 池：短线动量大池，cutover 时约 1784 个 active symbol。
- A 池：用户 long-thesis 清单；用户填 `config/a_pool.yaml` 前保持空骨架。

运行环境：

- production：LightOS，repo 在 `~/us-stock-research/`，Postgres 17 跑在 `localhost:5432`，系统时区 UTC。
- Codex workspace：Windows PowerShell，路径 `D:\Dev\us-stock-research\`。
- 远端部署由用户执行。Codex 不 SSH。

cutover 基线：

- 交接时 Git HEAD：`4348cbc chore(deploy): readme troubleshooting + cron tz + alert_log category`。
- 备份：`/lzcapp/document/usstock-backups/usstock-cutover-2026-04-30.sql.gz`，约 126MB。
- LightOS `.env` 位于 repo root，权限 600，用户保管。
- A 池在用户填写 thesis YAML 前预期为 0 行。

## V5+1 已知问题

| ID | 现象 | 根因 | V5+1 patch |
| --- | --- | --- | --- |
| P1 | migrate 报 `fe_sendauth: no password supplied`。 | CLI 没加载 repo `.env`。 | 在共享 DB 模块加载 `.env`。 |
| P2 | `postgresql://` 会尝试 `psycopg2`。 | SQLAlchemy 默认选 v2 driver。 | normalize 为 `postgresql+psycopg://`。 |
| P3 | `CREATE INDEX` 因旧表缺 `asset_class` 等列失败。 | DDL 在旧表 `ALTER ADD COLUMN` 前建 index。 | DDL 重排：create table、alter column、再 create index。 |
| P4 | `corporate_actions` / `fundamentals` 打出大量 `NoneType` ERROR。 | FMP tier 不支持端点，best-effort skip 记录得太吵。 | expected skip 降为 INFO / progress。 |
| P5 | `.bak.*` 备份文件可能进入 commit。 | 缺 ignore 规则。 | 加 `.gitignore` pattern。 |
| P6 | V5+1 缺 changelog / retro。 | cutover 工作需要归档。 | 加 changelog 与 change note。 |

不在 V5+1 范围：

- Hermes MCP client-side 接入。
- 节假日 sentinel。
- GCP 旧资源删除。
- secrets 轮换。
- `master` -> `main` 改名。
- 旧 Notion A 池 DB 删除。

## cutover 状态不明时的首个诊断

用户在 LightOS 跑：

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

默认路径：即使诊断噪音较多，也先在本地完成 V5+1 P1-P6，push main/master 后让用户 pull 并重跑。

## V5+1 push 后

用户侧流程：

```bash
cd ~/us-stock-research
git pull origin master
uv sync

# P1/P2/P3 验证：无需 source .env，且 migrate 幂等。
uv run python -m usstock_data.schema.migrate
```

重跑 2026-04-29：

```bash
cd ~/us-stock-research
DATE=2026-04-29

uv run --package usstock-data usstock-data daily --as-of $DATE
uv run --package usstock-analytics usstock-analytics themes-score --date $DATE
uv run --package usstock-analytics usstock-analytics a-pool signals --date $DATE
uv run --package usstock-analytics usstock-analytics signals --date $DATE --pool m
uv run --package usstock-reports usstock-reports daily --date $DATE --no-discord
```

预期：

| 步骤 | 预期结果 |
| --- | --- |
| data daily | quotes 约 1784、macro 1、indicators 约 1784、corp/fund best-effort skip |
| themes-score | `themes_score_daily` 31 行 |
| a-pool signals | A 池 YAML 为空时 0 行 |
| m-pool signals | M 信号行数随市场状态变化 |
| reports | Notion daily row + page；使用 `--no-discord` 时不发 Discord |

## cron 部署

用户复制 deploy scripts：

```bash
cd ~/us-stock-research
cp deploy/daily.sh ~/scripts/daily.sh
cp deploy/weekly_backup.sh ~/scripts/weekly_backup.sh
chmod +x ~/scripts/*.sh
```

UTC cron：

```cron
30 22 * * 1-5 /home/naivedog/scripts/daily.sh
0 20 * * 6 /home/naivedog/scripts/weekly_backup.sh
```

Asia/Shanghai 等价：

```cron
30 6 * * 2-6 /home/naivedog/scripts/daily.sh
0 4 * * 0 /home/naivedog/scripts/weekly_backup.sh
```

除非用户明确变更 ops policy，否则保持系统时区 UTC。

## 最终验收

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

通过标准：

- 5 个 rerun step 全部 exit 0。
- alert 噪音只剩已知 best-effort 类。
- quotes / indicators 约等于 active M 池规模，macro = 1。
- Notion daily DB 有 2026-04-29 row 和 page。
- `--no-discord` 验收期不发 Discord。

## 用户保留后续

cutover 通过后，用户可填写：

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

COHR、MRVL、WDC、SNDK 如需加入也由用户填写。thesis 数字和业务文字属于用户保留事项。
