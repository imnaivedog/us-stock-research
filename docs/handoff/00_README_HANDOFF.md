# Handoff 入口

先读 `docs/README.md`。本页刻意保持很短，避免出现两个真正的 docs 入口。

当前阶段：

- 阶段 0 docs restructure 已完成，等待用户 review。
- 用户批准前，不进入 P1。
- P1 来源：`docs/handoff/04_V5_PLUS_1_TASKBOOK.md`。
- cutover 状态与剩余命令：`docs/handoff/cutover.md`。
- 用户保留边界：`docs/handoff/USER_OWNED.md`。

硬边界：

- `_raw/` 只读。
- `USER_OWNED.md` 用户保留。
- Codex 不 SSH LightOS。
- 代码行为变更时，同 commit 更新 docs。

## 验收协议

每个 patch push 完后 · codex 必须按以下格式输出 · 用户照单跳验收。

### 1. Commit
<hash> <commit message>

### 2. 改动摘要 + Sandbox 自验
（继续保持现有格式 · pytest / ruff 等)

### 3. 🐧 LightOS 验收（用户跑）

```

cd ~/us-stock-research

git pull origin main

git log --oneline -3 # 期望看到 <hash>

uv sync # 如有依赖变化才必须

<针对 patch 实际效果的关键验证命令 · read-only 优先>

```

### 4. 期望输出

具体到"看到 X passed" / "ticker 列表含 TSLA / MSFT" / 
"返回 5 行" 这种秒判级 · 不要"应该正常"这种含糊话。

### 5. 失败排查

| 症状 | 大概原因 | 怎么办 |
| ... | ... | ... |

最多 3 行 · 覆盖最常见的报错。

### 6. 完成判定

- 全过 · 用户回复："P<n> 验收通过 · 进 P<n+1>"
- 任何失败 · 用户把报错原文贴回 · codex 修

### 设计原则

- 命令必须针对 patch 的实际效果 · 不写 boilerplate
  - 反例：P1 改 .env 加载 · 不应让用户跑 schema migrate
  - 正例：P1 应让用户在不 export DATABASE_URL 的情况下跑 read-only 命令
- read-only 优先 · 避免破坏性副作用（不动 DB · 不重启服务 · 不改环境）
- 不要求用户重启 daemon / cron / systemd 单元
- 一次验收 ≤ 5 步
- 失败排查 ≤ 3 行
- 命令一段 bash 块内连贴 · 用户能一次复制
