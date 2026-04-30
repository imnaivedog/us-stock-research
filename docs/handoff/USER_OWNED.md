# USER_OWNED

# USER_OWNED · 用户保留事项 · codex 不要做

> 本文件列出由 Naive Dog（项目所有者）保留 · codex 不要主动触碰的事项。
> 

> codex 如果发现这里的事项需要变更 · 请在 chat 提醒用户 · **不要直接动手**。
> 

## 1. 凭据管理（绝对边界）

Codex 永远不接触实际值。只看到 `.env` 里的 KEY 名（见 `ops/lightos-runtime.md` §3）。

- 6 个 secrets 轮换：
    - `FMP_API_KEY` / `FRED_API_KEY` / `POLYGON_API_KEY`
    - `NOTION_TOKEN`
    - `DISCORD_WEBHOOK_URL`
    - Postgres 业务密码 `POSTGRES_PASSWORD`
- LightOS SSH 端口 2222 / 用户 / 密码
- `.env` 文件实际值（codex 只看 KEY 名 · 不看 VALUE）
- `GOOGLE_APPLICATION_CREDENTIALS`（A 池 LLM verdict 用 Vertex AI · 用户后续配 · 还没加）
- `.env` 备份保管

## 2. 业务判断（域知识属于用户）

- A 池 thesis 的具体数字：`thesis_stop_mcap_b` / `target_mcap_b`
    - codex 不能猜 · 只能写 placeholder
    - 用户 vim `config/a_pool.yaml` 填
- A 池新增/移除 thesis 决定（codex 不主动 add/remove · 只在用户提供 yaml 时同步）
- `themes.yaml` 主题增减 · 权重调整
- 是否上线 a 池 / 推迟 / 改方向
- thesis 业务文字（`thesis_summary` 内容）

## 3. 部署运维（用户在 LightOS 跑）

- LightOS terminal 命令（codex 不直接 ssh · Win 无 bash/WSL · 凭据安全）
- crontab 安装/修改
- pg_dump 备份策略调整 · backup 文件管理
- 系统时区调整（当前 UTC · **不要改**）
- LightOS .env 文件直接编辑

## 4. 历史治理（不要主动清理）

- LightOS git stash `lightos-pre-V57-cutover-2026-04-30`（用户决定何时 drop）
- LightOS `scripts/compute_indicators.py.bak.20260430`（用户手动 rm）
- GCP 旧资源 5/7 删（用户的事 · 不在 repo 范围）
- `master` → `main` 改名（用户决定时机 · codex 协助执行 · 不主动）
- 旧 Notion 长线池 A 池 DB 删除（用户的事）

## 5. 文档治理边界

- Notion 上的页面（核心逻辑 / ADR / 原则 / 标的池 等）：repo `docs/core/` 是 SoT · Notion 是只读副本
- codex 改 `docs/` 时**不需要**也不应该尝试同步回 Notion · 用户偶尔手动同步即可
- Hermes SOP / LightOS 迁移记录 这两页留在 Notion · codex 不管

## 6. 跨工具协作

- Hermes 端 MCP 接入实装（`usstock-mcp` 工具签名 codex 维护 · Hermes 端用户/上游团队接入）
- Notion 页面权限 / 分享（用户在 Notion UI 改）
- Discord webhook 接入端（用户在 Discord 配）

## 7. 沟通约定（codex 提案 · 用户拍板）

Codex 在以下场景必须先在 chat 提案 · 用户确认后再动：

- **大方向变更**: 架构重构 / 新模块 / 废弃模块
- **数据迁移**: `DROP TABLE` / 大量改写历史数据 / 字段重命名
- **强制 push**: `git push --force` / `git reset --hard` 后 push
- **依赖升级**: Python 大版本 / Postgres 大版本 / uv 大版本
- **API 切换**: FMP → Polygon / Massive / AlphaVantage（V5+2 已规划 · 但仍需用户确认时机）

## 8. 协作模式（V5+1 已定 · 不切）

- **A 模式**: codex 在 Win 本地 `D:\Dev\us-stock-research\` 改代码 · 每 patch 独立 commit 直推 `origin master` · 用户在 LightOS terminal `git pull` + 跑命令
- **codex 不直接 ssh LightOS**（Win 无 bash/WSL · 凭据安全 · 不可靠）
- 切 B 模式（codex 全控）需用户明确指令 · 当前阶段不切

## 9. 边界总结表

| 事项 | 谁做 | codex 角色 |
| --- | --- | --- |
| 写代码 / 测试 / docs | codex | 主战场 |
| 跑 LightOS 命令 | 用户 | 不碰 |
| 凭据 / .env 管理 | 用户 | 只读 KEY 名 |
| A 池 thesis 业务数字 | 用户 | placeholder |
| themes.yaml 主题增删 | 用户 | 同步代码不改 yaml |
| 大架构变更 | 用户拍板 | 提案 |
| Notion 同步 | 用户 | 不同步 |
| Hermes 接入 | 用户/上游 | 维护工具签名 |
| GCP / 旧资源清理 | 用户 | 不管 |