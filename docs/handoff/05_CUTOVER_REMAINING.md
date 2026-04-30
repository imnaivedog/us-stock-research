# 05 · 剩余 Cutover 命令

<aside>
🏁

**V5+1 全部 6 个 patch push 完后 · 用户在 LightOS 跑这个文件里的命令收尾。**你（codex）告诉用户「按 05 文件收尾 · 卡住找我」。

</aside>

## 前置（V5+1 push 完后用户跑）

```bash
# LightOS terminal（用户已登录）
cd ~/us-stock-research

# 1. 拉 V5+1
git pull origin master  # 应看到 6 个新 commit

# 2. 同步依赖（P1 加了 python-dotenv 的话）
uv sync

# 3. 验证 P1：现在不需 source .env 也能 migrate
uv run python -m usstock_data.schema.migrate
# 应输出 Schema migration complete · 纯幂等 · 0 报错
```

**如果报错**：贴报错给 codex · codex 修。

## Phase 4 重跑 daily 流水线（DATE=2026-04-29）

```bash
cd ~/us-stock-research
DATE=2026-04-29

# 步 1：daily ETL（P4 修后无 ERROR 海 · ~5-15 分钟）
echo "=== Step 1: daily ETL ==="
time uv run --package usstock-data usstock-data daily --as-of $DATE

# 步 2：themes-score
echo "=== Step 2: themes-score ==="
uv run --package usstock-analytics usstock-analytics themes-score --date $DATE

# 步 3：a-pool signals（应 0 行 · a 池空骨架）
echo "=== Step 3: a-pool signals ==="
uv run --package usstock-analytics usstock-analytics a-pool signals --date $DATE

# 步 4：m-pool signals
echo "=== Step 4: m-pool signals ==="
uv run --package usstock-analytics usstock-analytics signals --date $DATE --pool m

# 步 5：reports（不发 Discord · 仅 Notion）
echo "=== Step 5: reports ==="
uv run --package usstock-reports usstock-reports daily --date $DATE --no-discord
```

**幂等性**：每一步都安全重跑（已验证）。中断了从中间步重跑就行。

**预期结果：**

| 步 | 输出 |
| --- | --- |
| 1 | quotes ~1784 / macro 1 / indicators ~1784 / corp 0 / fund 0（best-effort） |
| 2 | themes_score_daily 31 行 |
| 3 | a_signals_daily 0 行（a 池空） |
| 4 | m_signals_daily ~N 行（取决于市场状态） |
| 5 | Notion daily DB 多 1 行 + 详情页 |

## Phase 5 部署 cron

```bash
cd ~/us-stock-research

# 1. 复制脚本到固定位置
cp deploy/daily.sh ~/scripts/daily.sh
cp deploy/weekly_backup.sh ~/scripts/weekly_backup.sh
chmod +x ~/scripts/*.sh

# 2. 检查脚本环境变量（应已自动从 .env 读取 · P1 修后）
# （脚本里也会 source .env · 双保险）

# 3. 装 cron（UTC 版本 · 因为系统时区 = UTC）
crontab -e
# 加：
# 30 22 * * 1-5 /home/naivedog/scripts/daily.sh
# 0 20 * * 6 /home/naivedog/scripts/weekly_backup.sh

# 4. 验证 cron 装上
crontab -l
```

**Asia/Shanghai 替代版本**（如果想本地时间运行 · 不推荐·系统时区 UTC）：

```
30 6 * * 2-6 /home/naivedog/scripts/daily.sh
0 4 * * 0 /home/naivedog/scripts/weekly_backup.sh
```

## Phase 6 验收

```bash
cd ~/us-stock-research
DATE=2026-04-29

# 1. 看 daily 日志（如果 cron 跑过的）
tail -50 ~/logs/daily-${DATE}.log 2>/dev/null || echo "(手动跑的没写日志)"

# 2. alert_log
PG_URL="${DATABASE_URL/postgresql+psycopg:\/\//postgresql:\/\/}"
psql "$PG_URL" -c "SELECT trade_date, severity, job_name, category, LEFT(message,80) AS msg FROM alert_log WHERE trade_date='$DATE' ORDER BY id DESC;"
# 应看到 ≤ 5 条 RED/YELLOW · 都是已知 best-effort 类（FMP 端点缺失）

# 3. 4 表行数验
psql "$PG_URL" <<'SQL'
SELECT 'quotes_daily' AS tbl, COUNT(*) FROM quotes_daily WHERE trade_date='2026-04-29'
UNION ALL SELECT 'macro_daily', COUNT(*) FROM macro_daily WHERE trade_date='2026-04-29'
UNION ALL SELECT 'daily_indicators', COUNT(*) FROM daily_indicators WHERE trade_date='2026-04-29'
UNION ALL SELECT 'm_signals_daily', COUNT(*) FROM m_signals_daily WHERE trade_date='2026-04-29'
ORDER BY tbl;
SQL

# 4. 浏览器验 Notion daily DB
# 打开 https://notion.so/<NOTION_DAILY_DB_ID>
# 应看到 2026-04-29 的新行 + 同名详情页（ETF Top 3 / 个股 Top 5 / a_pool highlights 0 个）

# 5. 残留清理
rm -f scripts/compute_indicators.py.bak.20260430

# 6. 备份 git stash 决定 drop
git stash list  # 应看到 lightos-pre-V57-cutover-2026-04-30
# 如果验收全过：
git stash drop
```

**验收通过标准：**

- ✅ 5 步全跑通 · 退出码 0
- ✅ alert_log RED ≤ 0 / YELLOW ≤ 5
- ✅ 4 表行数健康（quotes/indicators ~1784 · macro 1 · m_signals 任意）
- ✅ Notion daily DB 多 1 行 + 详情页可点开
- ✅ Discord 没发（用了 --no-discord · 验收期）

## §8.3 用户手动（步 20-21 · 验收完成后）

### 步 20：vim a_pool.yaml 填 5 thesis

```bash
cd ~/us-stock-research
vim config/a_pool.yaml
```

填入（草案 · 用户可改）：

```yaml
- symbol: LITE
  status: watching
  added: 2026-04-29
  thesis_url: <Notion LITE 页 URL · 用户从浏览器复制>
  thesis_stop_mcap_b: <用户填>
  target_mcap_b: <用户填>

- symbol: COHR
  ...

- symbol: MRVL
  ...

- symbol: WDC
  ...

- symbol: SNDK
  ...
```

提交：

```bash
git add config/a_pool.yaml
git commit -m "feat(config): a_pool.yaml 填入 5 个长线 thesis (LITE/COHR/MRVL/WDC/SNDK)"
git push origin master
```

重跑 a-pool sync + signals 验：

```bash
uv run --package usstock-data usstock-data universe sync  # 同步 5 个 thesis 到 symbol_universe
uv run --package usstock-analytics usstock-analytics a-pool signals --date 2026-04-29  # 应看到 5 个 a 池信号
```

### 步 21：review themes.yaml

```bash
vim config/themes.yaml
# 验证 31 主题 / 头 8 / 关键字段（symbol_etf_anchor / quintile_thresholds 等）
```

如果耧得 OK · 不改。如果改了 · commit + push。

## 回滚预案（验收挂了走这个）

### 数据回滚

```bash
# LightOS：从 cutover 前备份还原
gunzip -c /lzcapp/document/usstock-backups/usstock-cutover-2026-04-30.sql.gz | psql "$PG_URL"
# ⚠️ 这会覆盖整个 usstock 数据库 · cutover 后的所有写入丢失
```

### 代码回滚

```bash
# 选项 A：git revert V5+1 commits
cd ~/us-stock-research
git log --oneline -10  # 找到 V5+1 6 个 commit hash
git revert <P1 hash> <P2 hash> ... <P6 hash>
git push origin master

# 选项 B：硬回 V5.7 cutover 起点
git reset --hard 4348cbc
git push --force-with-lease origin master  # ⚠️ 危险 · 会丢 V5+1 所有 commit

# 选项 C：用 V4 stash 还原
git stash list  # 找 stash@{0}: lightos-pre-V57-cutover-2026-04-30
git stash pop
```

### .env 回滚

```bash
# DATABASE_URL 改回（如果 P2 没修好）
sed -i 's|^DATABASE_URL=postgresql+psycopg://|DATABASE_URL=postgresql://|' .env
```

## 完成后跟 codex 报

> 「Phase 4-6 都过了 · 步 20-21 也填了 · cutover 收尾完成。LightOS 4-30 备份可以保留 · git stash 已 drop。下个 daily 等 5-1 cron 跑（UTC 22:30）。」
> 

Codex 这边可以：

- 更新 V5.7 task book 状态为 ✅ 完成
- 或开始计划 V5+2（FMP→Polygon 切换 / Hermes MCP 实接 / 节假日哨兵 / 业务密码强化 / master→main / 6 secrets 轮换 / 等）

## 这个交接包使命完成

读到这里你已经掌握了全部交接内容。起步：

1. 你在 chat 里跟用户说：「读完 6 个文件 · 明白了。先请跑 02 文件里的诊断三连· 贴结果给我· 我判断后决定是先修 V5+1 还是先重跑 daily」
2. 用户贴结果后 · 你按默认推荐路径（先修 V5+1）· 开始动 P1
3. 一路到 P6 push 完 · 跟用户说 ·「V5+1 完成 · 请按 05 文件 Phase 4-6 收尾」