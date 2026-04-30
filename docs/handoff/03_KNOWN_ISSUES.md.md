# 03 · 已知 Bug 清单

<aside>
🐛

读完掌握：5 个已知 bug 的根因 + 已用兜底 + V5+1 怎么永久修。这是 04 任务书的输入。

</aside>

## Bug 速查表

| # | 现象 | 根因 | cutover 兜底 | V5+1 |
| --- | --- | --- | --- | --- |
| 1 | migrate 时 `fe_sendauth: no password supplied` | CLI 入口未 load_dotenv | `set -a; source .env; set +a` | **P1 永久修** |
| 2 | `ModuleNotFoundError: psycopg2` | SQLAlchemy `postgresql://` 默认走 v2 driver · 但只装 v3 | sed 改前缀 → `postgresql+psycopg://` | **P2 永久修** |
| 3 | `UndefinedColumn: asset_class` 在 CREATE INDEX | ddl.sql 顺序：CREATE INDEX 在 ALTER 之前 · 旧表无新列 INDEX 挂 | preflight 28 ALTER 单跑 | **P3 永久修** |
| 4 | `corporate_actions` 1784 全 Skip NoneType ERROR 海 | FMP free tier 不支持 stock_dividend/split 端点 | best-effort 0 行不阻塞 | **P4 ERROR→INFO** |
| 5 | `fundamentals` 1784 全 Skip NoneType ERROR 海 | FMP starter 不支持 income statement | 同 4 | **P4 ERROR→INFO** |

## Bug 1 详情：[migrate.py](http://migrate.py) 不读 .env

**现象（用户看到的报错）：**

```
psycopg.OperationalError: connection failed: connection to server at "127.0.0.1", port 5432 failed: fe_sendauth: no password supplied
```

**根因：**

- `usstock-data` 包的 CLI 入口（schema.migrate / 其他子命令）依赖环境变量 `DATABASE_URL` `POSTGRES_*` 等
- 但代码里没在 `db.py` 或 CLI 入口调 `load_dotenv()`
- LightOS 终端默认不自动 source .env · 所以 Python 进程拿不到这些变量
- Postgres 收到无密码连接 → 拒绝

**cutover 兜底**：每次 ssh 重连后跑 `set -a; source .env; set +a`

**V5+1 P1 修复**（见 04 文件）：在 `db.py` 顶部 import 时调 `load_dotenv()` · 让所有 CLI 入口自动读 .env。

## Bug 2 详情：postgresql:// 走 psycopg2

**现象（用户看到的报错）：**

```
File "/.../sqlalchemy/dialects/postgresql/psycopg2.py", line 690, in import_dbapi
    import psycopg2
ModuleNotFoundError: No module named 'psycopg2'
```

**根因：**

- SQLAlchemy 2.x 看到 `postgresql://` 默认匹配 psycopg2 dialect（v2）
- V5 瘦身依赖只装了 psycopg v3（不是 v2）
- import psycopg2 失败 · 报错

**cutover 兜底**：sed 改 .env 把 `DATABASE_URL=postgresql://...` 改成 `DATABASE_URL=postgresql+psycopg://...` 显式指定 v3 dialect

**V5+1 P2 修复**：在 `db.py` `create_engine` 时自动检测 `postgresql://` 前缀 · 改写成 `postgresql+psycopg://` · 这样用户 .env 不需要写 SQLAlchemy 私有方言。

⚠️ **注意**：

- pg_dump 用 db name 直连 · 不依赖 URL 前缀 · 不影响 weekly_backup
- psql 调用前需要剥前缀（cutover 命令里有：`PG_URL="${DATABASE_URL/postgresql+psycopg:\/\//postgresql:\/\/}"`）
- P2 修完后 · 用户 .env 可以改回 `postgresql://` 也可以保留 `postgresql+psycopg://` · 都能工作

## Bug 3 详情：ddl.sql 顺序错

**现象（用户看到的报错）：**

```
psycopg.errors.UndefinedColumn: 字段 "asset_class" 不存在
[SQL: CREATE TABLE IF NOT EXISTS quotes_daily (...asset_class...);
CREATE INDEX IF NOT EXISTS idx_quotes_asset_class ON quotes_daily(asset_class);
... (其他表)
ALTER TABLE quotes_daily ADD COLUMN IF NOT EXISTS asset_class TEXT NOT NULL DEFAULT 'equity';]
```

**根因：**

- `CREATE TABLE IF NOT EXISTS quotes_daily (...asset_class...)` 跳过（旧 V4 表已存在 · 但无 asset_class 列）
- 紧跟的 `CREATE INDEX idx_quotes_asset_class ON quotes_daily(asset_class)` 引用不存在的列 → 挂
- 文件末尾的 `ALTER TABLE ... ADD COLUMN IF NOT EXISTS asset_class` 没机会执行

**cutover 兜底**：grep 抽出所有 ALTER TABLE → uv run python 一行行单事务跑 → 28 OK / 0 FAIL → 然后重跑 schema.migrate（CREATE INDEX 此时找到列 · 全幂等通过）

**V5+1 P3 修复**：重组 `ddl.sql` · 把所有 ALTER TABLE 提到 CREATE INDEX 之前 · 让 idempotent migrate 顺序正确。

## Bug 4 + 5 详情：FMP 端点缺失

**现象（用户看到的报错）：**

```
2026-04-30 18:50:21 | ERROR | usstock_data.etl.corporate_actions:run:97 - Skipping corporate actions for AAPL
NoneType: None
... (1784 行类似)
2026-04-30 18:50:21 | INFO | usstock_data.cli:run_daily:83 - data daily step finished: corporate_actions rows=0
```

fundamentals 同样模式。

**根因：**

- FMP **free / starter tier** 不包含：
    - `/v3/historical-price-full/stock_dividend/{symbol}`
    - `/v3/historical-price-full/stock_split/{symbol}`
    - `/v3/income-statement/{symbol}`（fundamentals）
- HTTP 401/403 · ETL catch 异常后返回 None
- ETL 用 `logger.error(...)` + `logger.exception(...)` 记 · 触发 NoneType: None 堆栈渲染
- 但 ETL 不抛 · pipeline 继续 · 写 0 行 · 不阻塞主信号链

**cutover 兜底**：忽略 ERROR 海 · 主信号链（quotes / macro / indicators / themes）不依赖这两个表

**V5+1 修复**：

- **P4 短期**：把 ETL 里 `logger.error` 降为 `logger.info`（带 best-effort 注释）· 减少 ERROR 海噪音 + 加进度计数（每 200 个一条 INFO「skipped 200/1784, success 0」）
- **后续（不在 V5+1）**：切换 provider 到 Polygon（已升级为 Massive）/ Alpha Vantage 等支持 free splits + dividends 的端点 · 或等 a 池上线再认真补 fundamentals

## Bug 6 潜在：Polygon→Massive 改名

**说明**：用户提到 Polygon 升级改名为「Massive」。当前 ETL 里的 polygon 调用代码（特别是 shares_outstanding ETL · 周更）是否还用 `polygon.io` 域名 · 没排查。

**V5+1 P4 顺手核查**：grep 整个 repo `polygon.io` · 看是否需要改成新域名。如果新域名生效 · 同步改。如果不确定 · 留 TODO 不改。

## 旧坑列表（不在 V5+1 范围 · 仅备录）

| 坑 | 说明 |
| --- | --- |
| Hermes MCP 占位 | usstock-mcp 4 工具已实装 · 但 Hermes 端实际接入还是占位 |
| 节假日哨兵 | 美股节假日没数据 · ETL 当前会写 0 行 · 后续加 holiday 检测跳过 |
| GCP 5/7 删 | cutover 完成后 · GCP 旧资源 5/7 删（用户记得） |
| 业务密码强化 | `ChangeMe2026Strong!` 太弱 · 后续轮换 |
| master→main | 后续把默认分支改名 |
| Notion-29 删 | A 池旧 DB · V5 部署后删 |
| atexit PermissionError | Win pytest 噪音 · 无害 · 不要乱修 |
| Win bash 不可用 | 你已知 · PowerShell 7 |
| LightOS git stash | `lightos-pre-V57-cutover-2026-04-30` · cutover 完用户决定 drop |
| `scripts/compute_indicators.py.bak.20260430` | LightOS 残留 · cutover 完手动 rm |
| 6 secrets 轮换 | 4 旧 + FRED + POLYGON 全部轮换 |

## 起步

继续读 `04_V5_PLUS_1_TASKBOOK.md`（你的主战场）。