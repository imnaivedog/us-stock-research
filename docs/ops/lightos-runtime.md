# lightos-runtime

# LightOS Runtime · 当前运行环境

> **不含凭据。** 所有 secrets 由用户管理 · 见 `handoff/USER_OWNED.md` §1。
> 

> 这里是 codex 需要知道的"系统当前在哪/怎么跑"。
> 

## 1. 主机

- **OS**: LightOS (容器化 Linux)
- **SSH**: 端口 2222 (宿主) → 22 (容器)
- **用户**: `naivedog`
- **HOME**: `/home/naivedog/`
- **时区**: 系统 = `UTC` (cron 用 UTC) · 用户偏好显示 `Asia/Shanghai`

## 2. Repo 路径

- **Repo**: `~/us-stock-research/` · git remote = `origin` (master)
- **venv**: `~/us-stock-research/.venv/` (uv 管)
- **uv**: `~/.local/bin/uv` (用户级 · 不走 sudo)
- **Python**: 3.12+ (uv 锁定 · `.python-version`)

## 3. .env 文件（13 KEY 名清单 · 不含值）

位置: `~/us-stock-research/.env` · 权限 600 · ~547 bytes

```bash
# 数据库
DATABASE_URL=postgresql+psycopg://...   # 注意：必须 postgresql+psycopg:// 前缀
POSTGRES_HOST
POSTGRES_PORT
POSTGRES_DB
POSTGRES_USER
POSTGRES_PASSWORD

# API keys
FMP_API_KEY
FRED_API_KEY
POLYGON_API_KEY
NOTION_TOKEN
NOTION_DAILY_DB_ID

# 集成
DISCORD_WEBHOOK_URL

# 运行
LOG_LEVEL=INFO
PYTHONUNBUFFERED=1
```

**缺**: `GOOGLE_APPLICATION_CREDENTIALS`（A 池 LLM verdict 用 Vertex AI · 用户后续配 · 见 USER_[OWNED.md](http://OWNED.md) §1）

## 4. Postgres（同机）

- **版本**: PostgreSQL 17
- **监听**: `localhost:5432`
- **DB**: `usstock`
- **User**: `stock_user`
- **数据规模 (cutover 当前)**:
    - `symbol_universe` ≈ 2358 (active m=1784 + V4 historical inactive 574 · a=0)
    - `quotes_daily` ≈ 1.82M+
    - `macro_daily` ≈ 1830
    - `daily_indicators` ≈ 450K

## 5. 关键路径

```
~/us-stock-research/         # repo
~/us-stock-research/.venv/   # virtualenv
~/us-stock-research/.env     # 13 KEY (600)
~/logs/                      # daily 日志
~/scripts/                   # 拷贝过来的 deploy/*.sh
/lzcapp/document/usstock-backups/   # weekly pg_dump 备份
```

## 6. Cron（系统 UTC）

```
# daily ETL · UTC 22:30 周一-五 = Asia/Shanghai 06:30 周二-六
30 22 * * 1-5 /home/naivedog/scripts/daily.sh >> /home/naivedog/logs/daily-$(date +\%F).log 2>&1

# weekly backup · UTC 20:00 周六 = Asia/Shanghai 04:00 周日
0 20 * * 6 /home/naivedog/scripts/weekly_backup.sh >> /home/naivedog/logs/backup-$(date +\%F).log 2>&1
```

双版本对照表（codex 改 cron 时同步两个时区都核一遍 · 防错）：

| Job | UTC 表达式 | Asia/Shanghai 等价 |
| --- | --- | --- |
| [daily.sh](http://daily.sh) | `30 22 * * 1-5` | `30 6 * * 2-6` |
| weekly_[backup.sh](http://backup.sh) | `0 20 * * 6` | `0 4 * * 0` |

## 7. SSH 重连约定

用户每次新开 SSH session 必跑（V5+1 P1 修后理论上不需要 · 但保留作 fallback）：

```bash
cd ~/us-stock-research && set -a && source .env && set +a
```

## 8. Win 本地（codex 工作位置）

- **Repo**: `D:\Dev\us-stock-research\`
- **PowerShell** 主 · `core.autocrlf=true`
- **bash/WSL 不可用** · codex 不直接 ssh LightOS（凭据安全 + 无 ssh 工具保证）
- pytest atexit `PermissionError` 是 Win .pyc 锁问题 · 无害

## 9. 已知运行环境陷阱

1. **DATABASE_URL 必须 `postgresql+psycopg://`** · 普通 `postgresql://` 走 psycopg2（缺包）
2. **psql 调用前必须剥前缀** · psql 不识别 `+psycopg`
3. **pg_dump 用 db name 直连** · 不走 DATABASE_URL 解析
4. **.env 加载** · V5+1 P1 之前 [db.py](http://db.py) 不主动 `load_dotenv` · ssh 重连必跑 §7 一行
5. **Markdown export 编码** · 用户在 Win export Notion → 中文需 UTF-8 (Win-1252 会 mojibake)

## 10. 健康检查（quick triage）

```bash
# 1. .env 是否加载
set -a && source ~/us-stock-research/.env && set +a && echo $DATABASE_URL

# 2. Postgres 通否
PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -d "$POSTGRES_DB" -c '\dt' | head

# 3. uv venv 通否
cd ~/us-stock-research && uv run python -c 'import sys; print(sys.version)'

# 4. cron 在跑否
crontab -l | grep -E 'daily|weekly'

# 5. 最新日志
tail -50 ~/logs/daily-$(date +%F).log
```