# 04 · V5+1 修补包任务书

<aside>
🛠️

**这是你的主战场。**6 个 patch · 每个独立 commit · 顺序提交 · 直推 master。读完这个文件 · 再读 05 看用户怎么用 V5+1 收尾。

</aside>

## 总览

| Patch | 文件 | 大小 | 验收 |
| --- | --- | --- | --- |
| **P1** | `db.py` | 加 ·5 行 | migrate 不需 source .env |
| **P2** | `db.py` | 加 ·10 行 | DATABASE_URL 可用 `postgresql://` |
| **P3** | `ddl.sql` | 重排序 | 旧表 + 新列幂等迁移成功 |
| **P4** | `etl/corporate_actions.py`  • `etl/fundamentals.py`  • polygon 域名 | 改 ·20 行 | ERROR 海消失 · 改 INFO 进度 |
| **P5** | `.gitignore` | 加 1 行 | 防备份文件入 commit |
| **P6** | `CHANGELOG.md`  • `docs/changes/2026-04-V5_PLUS_1.md` | 新增 | 复盘记录 |

**测试要求：**

- `uv run --package usstock-data pytest` 全绿（24 + 你为 P1/P2/P3 加的新测试）
- `uv run --package usstock-analytics pytest` 30 全绿
- `uv run --package usstock-reports pytest` 13 全绿
- `uv run ruff check` 全绿

## P1 - [db.py](http://db.py) load_dotenv

**目标**：让所有 CLI 入口（migrate / universe / daily / themes / signals / reports / mcp）自动读 `.env` · 用户不需要 source。

**文件**：`packages/usstock-data/src/usstock_data/db.py`

**diff 示意：**

```diff
+ from pathlib import Path
+ from dotenv import load_dotenv
  
+ # 自动加载 repo 根目录的 .env（无论 cwd 在哪）
+ _REPO_ROOT = Path(__file__).resolve().parents[4]
+ _ENV_FILE = _REPO_ROOT / ".env"
+ if _ENV_FILE.exists():
+     load_dotenv(_ENV_FILE)
  
  import os
  from sqlalchemy import create_engine
  ...
```

**注意**：

- `parents[4]` 取决于实际目录深度（`db.py` 在 `packages/usstock-data/src/usstock_data/db.py` → 4 层到 repo 根）· 验证一下层数对
- `python-dotenv` 已在 `usstock-data` dependencies 里？没的话加进 `packages/usstock-data/pyproject.toml`
- 不要覆盖已存在的 env var（`load_dotenv` 默认 `override=False` · 这是对的）

**单测（新加）：**

```python
def test_load_dotenv_called(tmp_path, monkeypatch):
    """db.py import 时应自动 load .env"""
    # 重新 import db 模块 · 验证 os.environ 被填充
    ...
```

**验收**：用户在 LightOS 跑 `uv run python -m usstock_data.schema.migrate`（不 source .env）· 应输出 Schema migration complete

**Commit**：`fix(data): db.py 自动 load_dotenv · CLI 入口不再依赖 source .env`

## P2 - postgresql:// 自动转 +psycopg

**目标**：用户 `.env` 写 `DATABASE_URL=postgresql://...` 也能工作 · 不强制写 SQLAlchemy 私有方言。

**文件**：`packages/usstock-data/src/usstock_data/db.py`

**diff 示意：**

```diff
  import os
  from sqlalchemy import create_engine
  
+ def _normalize_db_url(url: str) -> str:
+     """把 postgresql:// 自动转成 postgresql+psycopg:// (psycopg v3 dialect)"""
+     if url.startswith("postgres://"):  # heroku 风格
+         url = url.replace("postgres://", "postgresql://", 1)
+     if url.startswith("postgresql://"):
+         return url.replace("postgresql://", "postgresql+psycopg://", 1)
+     return url
  
  def get_engine():
-     return create_engine(os.environ["DATABASE_URL"], future=True)
+     return create_engine(_normalize_db_url(os.environ["DATABASE_URL"]), future=True)
```

**注意**：

- 已有 `postgresql+psycopg://` 的 URL 不动
- weekly_[backup.sh](http://backup.sh) 里的 pg_dump 用 `POSTGRES_DB` 等单独变量 · 不依赖 DATABASE_URL · 不需改
- 检查 repo 其他地方有没直接 `os.environ["DATABASE_URL"]` 传给 create_engine 的 · 都调 `_normalize_db_url`

**单测：**

```python
def test_normalize_db_url_postgresql():
    assert _normalize_db_url("postgresql://u:p@h/d") == "postgresql+psycopg://u:p@h/d"

def test_normalize_db_url_already_psycopg():
    assert _normalize_db_url("postgresql+psycopg://u:p@h/d") == "postgresql+psycopg://u:p@h/d"

def test_normalize_db_url_heroku_postgres():
    assert _normalize_db_url("postgres://u:p@h/d") == "postgresql+psycopg://u:p@h/d"
```

**验收**：用户在 LightOS 把 .env 改回 `postgresql://` 跑 migrate · 应成功

**Commit**：`fix(data): db.py 自动转 postgresql:// → postgresql+psycopg:// (v3 dialect)`

## P3 - ddl.sql 重排序

**目标**：把所有 `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` 提到 `CREATE INDEX` 之前 · 让 idempotent migrate 顺序正确。

**文件**：`packages/usstock-data/src/usstock_data/schema/ddl.sql`

**新结构（3 阶段）：**

```sql
-- ============================================================
-- PHASE 1: CREATE TABLE IF NOT EXISTS (所有表)
-- ============================================================
CREATE TABLE IF NOT EXISTS quotes_daily (... asset_class TEXT ...);
CREATE TABLE IF NOT EXISTS macro_daily (... silver NUMERIC ...);
... (其他 22 张表)

-- ============================================================
-- PHASE 2: ALTER TABLE ADD COLUMN IF NOT EXISTS (补旧表的新列)
-- ============================================================
ALTER TABLE quotes_daily ADD COLUMN IF NOT EXISTS asset_class TEXT NOT NULL DEFAULT 'equity';
ALTER TABLE macro_daily ADD COLUMN IF NOT EXISTS silver NUMERIC(18,4);
... (28 行 ALTER · 详见下面)

-- ============================================================
-- PHASE 3: CREATE INDEX IF NOT EXISTS (此时所有列都存在)
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_quotes_asset_class ON quotes_daily(asset_class);
CREATE INDEX IF NOT EXISTS idx_macro_silver ON macro_daily(silver);
...
```

**已知 28 行 ALTER 列表（cutover 期间提取出的 · 原封不动拷进 Phase 2）：**

```sql
ALTER TABLE quotes_daily ADD COLUMN IF NOT EXISTS asset_class TEXT NOT NULL DEFAULT 'equity';
ALTER TABLE macro_daily ADD COLUMN IF NOT EXISTS silver NUMERIC(18,4);
ALTER TABLE macro_daily ADD COLUMN IF NOT EXISTS gold_silver_ratio NUMERIC(18,4);
ALTER TABLE macro_daily ADD COLUMN IF NOT EXISTS hyg_lqd_spread NUMERIC(18,4);
ALTER TABLE macro_daily ADD COLUMN IF NOT EXISTS ief NUMERIC(18,4);
ALTER TABLE macro_daily ADD COLUMN IF NOT EXISTS dxy NUMERIC(18,4);
ALTER TABLE macro_daily ADD COLUMN IF NOT EXISTS wti NUMERIC(18,4);
ALTER TABLE macro_daily ADD COLUMN IF NOT EXISTS btc NUMERIC(18,4);
ALTER TABLE macro_daily ADD COLUMN IF NOT EXISTS us10y NUMERIC(18,4);
ALTER TABLE macro_daily ADD COLUMN IF NOT EXISTS us2y NUMERIC(18,4);
ALTER TABLE macro_daily ADD COLUMN IF NOT EXISTS dgs10 NUMERIC(18,4);
ALTER TABLE macro_daily ADD COLUMN IF NOT EXISTS dgs2 NUMERIC(18,4);
ALTER TABLE macro_daily ADD COLUMN IF NOT EXISTS spread_10y_2y NUMERIC(18,4);
ALTER TABLE symbol_universe ADD COLUMN IF NOT EXISTS pool TEXT NOT NULL DEFAULT 'm';
ALTER TABLE symbol_universe ADD COLUMN IF NOT EXISTS thesis_url TEXT;
ALTER TABLE symbol_universe ADD COLUMN IF NOT EXISTS shares_outstanding NUMERIC;
ALTER TABLE symbol_universe ADD COLUMN IF NOT EXISTS shares_outstanding_updated_at TIMESTAMPTZ;
ALTER TABLE symbol_universe ADD COLUMN IF NOT EXISTS thesis_added_at TIMESTAMPTZ;
ALTER TABLE symbol_universe DROP COLUMN IF EXISTS target_cap;
ALTER TABLE symbol_universe DROP COLUMN IF EXISTS target_market_cap;
ALTER TABLE symbol_universe_changes ADD COLUMN IF NOT EXISTS pool TEXT;
ALTER TABLE symbol_universe_changes ADD COLUMN IF NOT EXISTS thesis_url TEXT;
ALTER TABLE symbol_universe_changes DROP COLUMN IF EXISTS target_cap;
ALTER TABLE symbol_universe_changes DROP COLUMN IF EXISTS target_market_cap;
ALTER TABLE alert_log ADD COLUMN IF NOT EXISTS category TEXT;
ALTER TABLE watchlist ADD COLUMN IF NOT EXISTS target_market_cap NUMERIC;
ALTER TABLE watchlist ADD COLUMN IF NOT EXISTS thesis_url VARCHAR;
ALTER TABLE watchlist ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
```

**注意**：

- 保留所有 `IF NOT EXISTS` · 保证幂等
- DROP COLUMN IF EXISTS 也归在 Phase 2（清理旧列 · 例如 `target_cap`）
- 不要把 PRIMARY KEY / UNIQUE 这种约束的索引拆出来 · 它们和 CREATE TABLE 同步生效

**单测（新加 `tests/test_schema_idempotent.py`）：**

```python
def test_migrate_idempotent_against_old_schema():
    """模拟旧表无新列 · migrate 应能补列再建索引"""
    # 1. 在测试 Postgres 建无 asset_class 的 quotes_daily
    # 2. 跑 migrate
    # 3. 验证 idx_quotes_asset_class 存在 · asset_class 列存在
    ...
```

**验收**：用户在 LightOS 跑 `uv run python -m usstock_data.schema.migrate` · 应输出 Schema migration complete · 纯幂等 · 0 报错

**Commit**：`fix(data): ddl.sql 三阶段重排 (CREATE TABLE → ALTER → CREATE INDEX) · 修旧表 idempotent migrate`

## P4 - corp/fund ERROR→INFO + polygon 域名核

**目标：**

1. 把 `corporate_actions` 和 `fundamentals` ETL 的 ERROR 海降为静默 INFO（每 200 个一条进度）· 用户日志干净
2. 顺手核查 polygon→Massive 域名是否需改

**文件：**

- `packages/usstock-data/src/usstock_data/etl/corporate_actions.py`
- `packages/usstock-data/src/usstock_data/etl/fundamentals.py`
- 全 repo grep `polygon.io`

**diff 示意（corporate_[actions.py](http://actions.py)）：**

```diff
+ skip_count = 0
+ success_count = 0
+ total = len(symbols)
+ 
  for symbol in symbols:
      try:
          data = fmp_client.get_corporate_actions(symbol)
          if data is None:
-             logger.error(f"Skipping corporate actions for {symbol}")
+             # FMP free/starter tier 不支持此端点 · best-effort 跳过
+             skip_count += 1
+             if skip_count % 200 == 0:
+                 logger.info(f"corporate_actions: skipped {skip_count}/{total}, success {success_count}")
              continue
          # 正常写入逻辑
          ...
+         success_count += 1
      except Exception:
-         logger.exception(f"Skipping corporate actions for {symbol}")
+         logger.debug(f"corporate_actions skip {symbol}", exc_info=True)
+         skip_count += 1

+ logger.info(f"corporate_actions done: {success_count} success / {skip_count} skipped / {total} total")
```

fundamentals 同样模式。

**polygon 域名核：**

```bash
cd D:\Dev\us-stock-research
git grep -n "polygon.io"
git grep -n "api.polygon"
```

如果有 hit · 改成 Massive 域名（用户没说具体新域名 · 让用户确认 · 或保留 [polygon.io](http://polygon.io) 因为 Massive 可能保留兼容）。

**注意**：不要改正常成功路径 · 只改 None 兜底分支 · 保留 ERROR 用于真正异常（例如 Postgres 写入失败 / API rate limit 429）

**单测（扩展）：**

```python
def test_corporate_actions_skip_on_none(caplog):
    """FMP 返回 None 时 · 应静默 skip · 不打 ERROR"""
    with patch("...get_corporate_actions", return_value=None):
        run([...])
    assert "ERROR" not in caplog.text
    assert "skipped" in caplog.text or "done" in caplog.text
```

**验收**：用户在 LightOS（V5+1 push 后）跑 `usstock-data daily --as-of 2026-04-29` · 应看到清爽日志（corporate_actions 一行总结 + fundamentals 一行总结 · 无 ERROR 海）

**Commit**：`fix(data): corporate_actions/fundamentals best-effort skip 静音 · ERROR→INFO 进度`

## P5 - .gitignore 加通配

**目标**：防以后类似 `.bak.*` 备份文件入 commit。

**文件**：`.gitignore`

**加几行：**

```
# 临时备份文件
*.bak.*
*.bak
*.bak.[0-9]*
```

**注意**：LightOS 上的 `scripts/compute_indicators.py.bak.20260430` 是 untracked · 不在 Win repo · 你不需要 git rm。用户在 05 文件被告知手动 `rm` LightOS 上的那个文件。

**Commit**：`chore(scripts): .gitignore 加 *.bak.* 通配 · 防备份残留入 commit`

## P6 - CHANGELOG + 复盘文档

**文件：**

- `CHANGELOG.md`（如果存在）
- `docs/changes/2026-04-V5_PLUS_1.md`（新建）

[**CHANGELOG.md](http://CHANGELOG.md) 新条目：**

```markdown
## [V5+1] - 2026-04-30

### Fixed
- `db.py` 自动 `load_dotenv()` · CLI 入口不再依赖 `source .env`（P1）
- `db.py` 自动转 `postgresql://` → `postgresql+psycopg://` · 兼容用户简洁写法（P2）
- `ddl.sql` 三阶段重排 · 修旧表 idempotent migrate（P3）
- `corporate_actions` / `fundamentals` ETL 静音 best-effort skip · ERROR 降 INFO 进度（P4）

### Chore
- `.gitignore` 加 `*.bak.*` 通配（P5）
```

**docs/changes/2026-04-V5_PLUS_[1.md](http://1.md)**（新建 · 复盘）：

```markdown
# V5+1 修补包复盘（2026-04-30）

## 背景

V5.7 cutover 期间发现 5 个代码 bug 阻塞 schema migrate / daily ETL。Cutover 用兜底命令绕过 · V5+1 修补包永久修。

## 5 个 bug 速查（详见 docs/handoff/cutover.md）

[列表]

## V5+1 vs cutover 兜底对照

| 问题 | cutover 兜底 | V5+1 永久修 |
|------|--------------|-------------|
| migrate 不读 .env | source .env | P1 db.py load_dotenv |
| postgresql:// 走 v2 | sed 改前缀 | P2 _normalize_db_url |
| ddl.sql 顺序错 | preflight ALTER | P3 三阶段重排 |
| corp/fund ERROR 海 | 忽略 | P4 INFO 进度 |

## 测试覆盖

- 新加 X 个测试 · 总数从 67 → X 全绿
- ruff 全绿
- UTF-8 干净

## 后续（不在 V5+1）

- corporate_actions / fundamentals 切 provider（FMP → Polygon/Massive）等 a 池上线
- 6 secrets 轮换
- master → main 改名
- 其他见 docs/handoff/cutover.md 旧坑列表
```

**Commit**：`docs: V5+1 修补包 CHANGELOG + 复盘文档`

## 提交策略

```bash
# Win 本地（你 codex 操作）：
cd D:\Dev\us-stock-research

# P1
git checkout master
git pull origin master  # 同步最新
# 改 db.py + pyproject.toml
git add packages/usstock-data/src/usstock_data/db.py
git add packages/usstock-data/pyproject.toml
git commit -m "fix(data): db.py 自动 load_dotenv · CLI 入口不再依赖 source .env"
git push origin master

# P2 同样套路
# P3 改 ddl.sql + 加测试 · commit · push
# P4 改两个 ETL + 加测试 · commit · push
# P5 改 .gitignore · commit · push
# P6 加 CHANGELOG + 复盘 · commit · push
```

每 patch push 后 · 跟用户说：

> 「P1 已 push · commit hash xxx · 你可以等所有 6 个 patch 都 push 后再 git pull · 或现在拉一次试 P1」
> 

**推荐全部 push 完再统一拉** · 减少用户切换次数。

## 起步

读完这个文件 · 继续读 `cutover.md`（V5+1 push 后用户怎么收尾）。
