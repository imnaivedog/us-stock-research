# Changelog

## [V5+1] - 2026-05-01

### Fixed

- `db.py` 自动 `load_dotenv()`，CLI 入口不再依赖 `source .env`（P1）。
- `db.py` 自动转 `postgres://` / `postgresql://` 到 `postgresql+psycopg://`，兼容用户简洁写法（P2）。
- data / analytics / reports 三层 DB helper 在 `DATABASE_URL` 缺 password 且 `POSTGRES_PASSWORD` 存在时自动补齐 password，修 cutover `fe_sendauth: no password supplied`。
- `ddl.sql` 三阶段重排，修旧表 idempotent migrate 中索引早于补列的问题（P3）。
- `corporate_actions` / `fundamentals` ETL 对 expected best-effort skip 降噪，普通 per-symbol skip 走 DEBUG + INFO 汇总，transient/provider outage 保留 ERROR（P4）。
- `earnings_calendar` 对 FMP 404 endpoint unavailable 走 best-effort skip，不再打断 `data daily`。
- deploy / cutover 命令改为 `origin main`，M-pool signals 不再带无效 `--pool m`。
- reports 的 risk dial 仓位映射对齐 ADR-004：S/A/B/C/D = 120%/100%/80%/60%/20%。
- A 池 12-signal 实现对齐 V5.7 contract：B1-B5 / S1-S3 / W1-W2 / `theme_oversold_entry` 不再使用旧的临时语义。
- A 池 `config/a_pool.yaml` 补入 5 只 `watching` skeleton，并恢复对应 thesis reference 文件。

### Chore

- `.gitignore` 加 `*.bak.*` / `*.bak` / `*.bak.[0-9]*` 通配，防备份文件进入 commit（P5）。
- `.gitignore` 加根 `logs/`，pytest 临时目录固定为 `.pytest_tmp`，减少 Windows 本地测试收尾噪音。
- cutover / runbook 多命令块加 `set -euo pipefail`，避免前序失败被后续命令掩盖。
- 补 V5+1 changelog 与复盘记录（P6）。
