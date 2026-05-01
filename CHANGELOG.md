# Changelog

## [V5+1] - 2026-05-01

### Fixed

- `db.py` 自动 `load_dotenv()`，CLI 入口不再依赖 `source .env`（P1）。
- `db.py` 自动转 `postgres://` / `postgresql://` 到 `postgresql+psycopg://`，兼容用户简洁写法（P2）。
- data / analytics / reports 三层 DB helper 在 `DATABASE_URL` 缺 password 且 `POSTGRES_PASSWORD` 存在时自动补齐 password，修 cutover `fe_sendauth: no password supplied`。
- `ddl.sql` 三阶段重排，修旧表 idempotent migrate 中索引早于补列的问题（P3）。
- `corporate_actions` / `fundamentals` ETL 对 expected best-effort skip 降噪，普通 per-symbol skip 走 DEBUG + INFO 汇总，transient/provider outage 保留 ERROR（P4）。
- cutover 文档命令改为 `origin main`，M-pool signals 不再带无效 `--pool m`。

### Chore

- `.gitignore` 加 `*.bak.*` / `*.bak` / `*.bak.[0-9]*` 通配，防备份文件进入 commit（P5）。
- `.gitignore` 加根 `logs/`，pytest 临时目录固定为 `.pytest_tmp`，减少 Windows 本地测试收尾噪音。
- 补 V5+1 changelog 与复盘记录（P6）。
