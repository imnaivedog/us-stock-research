# 02 · Cutover 当前进度

<aside>
📍

读完知道：cutover 已经做了什么 / 卡在哪 / 你第一件事（让用户跑诊断三连 · 确认 daily ETL 状态）。

</aside>

## 时间线（2026-04-30 Asia/Shanghai）

| 时间 | 阶段 | 结果 |
| --- | --- | --- |
| 17:00 | Phase 0-1 | ssh + timedatectl=UTC + .env 注入 FRED/POLYGON ✅ |
| 17:30 | Phase 2 | 备份 126MB + git stash + git pull 4348cbc + uv sync ✅ |
| 18:30 | Phase 3 schema | migrate 完成（3 个兜底）✅ |
| 18:36 | Phase 3 universe | sync 完成 m=1784 / a=0 ✅ |
| 18:50 | Phase 4-1 daily ETL | 启动 · DATE=2026-04-29 |
| 19:08 | Phase 4-1 fundamentals | 1784 全 Skip NoneType（FMP 不支持端点） |
| 20:26 | 切交接 | daily 状态 **未确认** |

## 已完成 ✅

- Phase 0：prerequisite
- Phase 1：ssh + timedatectl=UTC + .env 注入 FRED/POLYGON
- Phase 2：备份 + git stash + git pull + uv sync
- Phase 3：
    - schema migrate 完成（用了 3 个兜底 · 见 03 文件 Bug 1-3）
    - universe sync 完成（m=1784 candidates / 1784 upserted / 375 removed · a=0 synced）
    - 22 表全到位 · A 池表头有但 0 数据行（符合预期）

## 卡在哪 🔵

**Phase 4 第 1 步：daily ETL（DATE=2026-04-29）**

跑了 ~70 分钟 · 用户切交接前看到：

- `corporate_actions`：1784 个 symbol 全 Skip · `NoneType: None` ERROR 海
- `fundamentals`：同上 · 至少前几百个 Skip · 用户没看到完成

**关键问题（codex 第一件事让用户确认）：**

1. daily 命令的退出码是 0 吗？
2. `quotes_daily` / `macro_daily` / `daily_indicators` 4-29 的行数是不是健康（~1784 / 1 / ~1784）？

如果是 → corp/fund 全 0 行不阻塞 · 直接推进 V5+1

如果不是 → 看 alert_log + V5+1 修完后用户重跑 daily（V5+1 P4 修完后会更安静）

## 待做（剩余 cutover）

- ❓ Phase 4 第 1 步状态确认（你第一件事）
- ⚪ Phase 4 步 2：themes-score
- ⚪ Phase 4 步 3：a-pool signals（应 0 行 · a 池空）
- ⚪ Phase 4 步 4：m-pool signals
- ⚪ Phase 4 步 5：reports daily --no-discord
- ⚪ Phase 5：cp deploy/*.sh ~/scripts/ + chmod + crontab UTC
- ⚪ Phase 6：tail log / alert_log / 4 表行数 / 浏览器开 Notion daily DB 验
- ⚪ §8.3 用户手动（步 20-21）：vim a_pool.yaml 5 thesis · review themes.yaml

## 你（codex）的第一件事

**不要立刻动代码。先告诉用户跑这一段诊断三连**（用户在 LightOS terminal 已登录 · `set -a; source .env; set +a` 已生效）：

```bash
cd ~/us-stock-research

# 1. 上一条 daily 命令的退出码
echo "=== daily exit code: $? ==="

# 2. 4-29 关键表行数
PG_URL="${DATABASE_URL/postgresql+psycopg:\/\//postgresql:\/\/}"
psql "$PG_URL" <<'SQL'
SELECT 'quotes_daily' AS tbl, COUNT(*) AS rows FROM quotes_daily WHERE trade_date='2026-04-29'
UNION ALL SELECT 'macro_daily', COUNT(*) FROM macro_daily WHERE trade_date='2026-04-29'
UNION ALL SELECT 'daily_indicators', COUNT(*) FROM daily_indicators WHERE trade_date='2026-04-29'
UNION ALL SELECT 'themes_members', COUNT(*) FROM themes_members
UNION ALL SELECT 'themes_master', COUNT(*) FROM themes_master
ORDER BY tbl;
SQL

# 3. alert_log 最近 2 小时
psql "$PG_URL" -c "SELECT trade_date, severity, job_name, category, LEFT(message,80) AS msg FROM alert_log WHERE created_at > NOW() - INTERVAL '2 hours' ORDER BY id DESC LIMIT 20;"
```

根据结果分支：

| 情景 | exit | quotes | indicators | 你怎么做 |
| --- | --- | --- | --- | --- |
| 健康 | 0 | ~1784 | ~1784 | 直接动 V5+1 P1-P6 修代码（看 04 文件） |
| 部分 | 0 | <1500 | <1500 | 看 alert_log · 决定先修 V5+1 还是先重跑 daily |
| 挂了 | 非 0 | * | * | 让用户贴最后 30 行日志 · 大概率 V5+1 P3/P4 修完后重跑就好 |

**默认推荐路径**：不论健康/部分/挂了 · 都先把 V5+1 P1-P6 干完 push master · 然后让用户 git pull + 重跑 daily。这样最干净。

## 起步

继续读 `03_KNOWN_ISSUES.md`（5 个 bug 详细根因）→ `04_V5_PLUS_1_TASKBOOK.md`（你的主战场）。