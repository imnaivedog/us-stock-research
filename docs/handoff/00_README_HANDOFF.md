# 00 · README · 交接给 Codex

# 00 · README · 交接给 codex

> Codex 先读这页。读完你能拿到 us-stock-research 项目的全貌 · 该做什么 · 去哪看。
> 

## ⚠️ 阶段 0：读 _raw/ → 自主重构 docs/

**你接手的第一件事不是写代码·是把文档结构定型。**

`docs/_raw/` 三个 source 文件是 Notion 原始页 export·**设计权威 + 完整性基准**。其它所有 docs/ 内容（除 `_raw/` 与 `USER_OWNED.md`）都是 cutover 期间快速整理稿·**结构 / 措辞 / 详略都可调**·你有完全自主权。

**阶段 0 任务**：

1. 读 `docs/_raw/` 三个 source（设计权威）
2. 读 `docs/handoff/00-05` 与 `USER_OWNED.md`（接手上下文 + 用户保留区）
3. 读现有 `docs/core/` `docs/ops/` `docs/changes/` `docs/reference/` 全部内容
4. **基于 _raw/ 检查完整性**：信号阈值 / 评分公式 / 字段语义 / ADR 状态 是否齐全且准确·哪些设计点 _raw/ 有但当前 docs/ 没有
5. **自主决定 docs/ 结构**：
    - 当前 5 子目录（core/ ops/ changes/ reference/ handoff/）只是建议·可重排可合并
    - 简化 · 删冗余 · 合并相近文件 · 标题精简
    - 该删的删 · 该重写的重写 · 优先 codex 视角而非用户视角
6. 一次 commit · message: `docs: restructure based on _raw/ source · simplify · drop redundant`
7. push origin master · 通知用户 · **等用户审完才进 P1**

**不动**：

- `docs/_raw/`（设计快照 · 只读）
- `docs/handoff/USER_OWNED.md`（用户保留区）
- `docs/handoff/04_V5_PLUS_1_TASKBOOK.md`（V5+1 patch 清单 · 阶段 1 用 · 内容保留 · 结构可调）
- 业务代码 / `schema/` / 配置 yaml

**冲突原则**：以 `_raw/` 为完整性基准 · 其它可全删重写。

**简化原则**：能合并不分文件 · 能删不留 · 标题精简 · 优先 codex 视角。

阶段 0 完成后 · 进阶段 1（详见末尾“提示词·阶段 1”）。

## TL;DR

- **项目** = 个人美股波段 + 长线辅助决策系统 · 1 人维护
- **你的角色** = 代码主始 · 上又股 + 本地 trunk 直推 origin master
- **用户** = Naive Dog · 验收 + 发部署指令 · 不改代码
- **部署** = 用户在 LightOS terminal 跳 git pull 与跑命令 · 你不 ssh LightOS
- **文档** = 本 `docs/` 下 5 个子目录 = SoT · 你负责随代码进化同 commit 更新

## 当前紧迫任务

1. 读 `04_V5_PLUS_1_TASKBOOK.md` · 6 个 patch 待交
2. 读 `03_KNOWN_ISSUES.md` · daily ETL corp/fund NoneType ERROR 海 · 源于 FMP free tier fallback
3. 读 `05_CUTOVER_REMAINING.md` · 收尾动作
4. 读 `core/` 5 个文件 · 你需要遵守的业务与架构决议
5. 动代码前·检查是否遵守 `core/principles.md` 与 `core/adr.md`

## 文档目录结构

```
docs/
├── handoff/                       # 交接专区 · 启动仓库读这里
│   ├── 00_README_HANDOFF.md       # 本页 · 总入口
│   ├── 01_CONTEXT_AND_ENV.md      # 背景 · 项目主问
│   ├── 02_STATUS.md               # cutover 当前进度
│   ├── 03_KNOWN_ISSUES.md         # bug 清单 + 临时 workaround
│   ├── 04_V5_PLUS_1_TASKBOOK.md   # 你首体 · 6 patch
│   ├── 05_CUTOVER_REMAINING.md    # 剩余 cutover 命令
│   └── USER_OWNED.md              # 不走你·用户保留事项
│
├── core/                          # 业务逻辑 SoT · 你随代码同 commit 更新
│   ├── core-logic.md              # 业务一句话 · daily 流 · 14 节
│   ├── principles.md              # 11 节事务原则 · 动手前看
│   ├── architecture.md            # 4 package + 22 表 + 12 信号 + MCP 契约
│   ├── stock-pool.md              # 双池 SoT 详解
│   └── adr.md                     # 33 条 ADR 索引
│
├── ops/                           # 运行与部署
│   ├── lightos-runtime.md         # 13 ENV / Postgres / cron / 路径 · 不含凭据
│   └── runbook.md                 # daily 怎么跑 / 看日志 / 备份 / 回滚
│
├── changes/                       # 变更日志
│   └── 2026-04-V5.7.md            # V5.7 任务书归档
│
└── reference/                     # 模板 / thesis 调查
    ├── thesis-template.md         # A 池 thesis 模板
    ├── thesis-LITE.md
    ├── thesis-COHR.md
    ├── thesis-MRVL.md
    ├── thesis-WDC.md
    └── thesis-SNDK.md
```

## docs as code 责任边界

- **docs/** 仓是 SoT · Notion 供用户阅读 · codex 不同步回 Notion
- **代码变更同 commit 更新文档**：schema 动 → update `core/architecture.md` 与 `core/adr.md`·信号逻辑动 → update `core/core-logic.md`·运行参数动 → update `ops/lightos-runtime.md`
- **用户使用 git pull 拉仓后 · 会看到文档与代码同走**
- **动 ADR 走追加**：不修旧 ADR·只加新 ADR 同时标旧 ADR 为 Superseded by ADR-XXX
- **你不负责**：export 回 Notion · 用户手动同步 Notion侧
- **遇到 USER_[OWNED.md](http://OWNED.md) 中的事项**：不动 · 该提错提错 · 别帮用户“代劳”

## 与 Hermes 的关系

- Hermes 是另一个项目 · 你不仁责任。
- 本项目与 Hermes 仅通过 **MCP** 接：`usstock-mcp` 提供 4 工具（`get_dial` / `get_top_themes` / `get_top_stocks(pool=m|a)` / `query_signals`）·返 raw structured。
- 细节见 `core/architecture.md` §Hermes MCP 契约。
- **你不需要了解** Hermes 的内部 / Hermes 的迁移历史 / Hermes 的代码。

## 运行环境一句话

- prod = LightOS · Postgres 17 · cron daily 22:30 UTC · 详见 `ops/lightos-runtime.md`
- dev = Win · PowerShell · uv · 本地 Postgres 5433 · 详见 `01_CONTEXT_AND_ENV.md`
- bash/WSL 不可用 · 你只能走 PowerShell

## 代码接手顺序建议

1. 读 `core/principles.md` · 记住永不做清单与起点问句表
2. 读 `core/core-logic.md` · 拿到业务全貌
3. 读 `core/architecture.md` · 代码布局·接口·表
4. 读 `core/stock-pool.md` · 双池与主题机制
5. 读 `core/adr.md` · 哪些决议不要走偏
6. 读 `04_V5_PLUS_1_TASKBOOK.md` · 根据你的补充调整 · 开始代码
7. 本地跑通测试 · 运行 `pytest -p no:cacheprovider`
8. trunk 直推 origin master · commit message 记明 patch ID + ADR ID
9. 同 commit 更新相关文档·避免代码与文档脱锅
10. 告知用户 · 用户去 LightOS 跳 git pull + 商定部署

## 中转词表

- **竹蜓蜓 / Notion AI** = 文档 + 审查 + Notion 侧 · 不代跳你写代码
- **A 池** = 拥有或却思考入场 · thesis 驱动 · SoT = config/a_pool.yaml
- **M 池** = 未拥有 · 主题 β 信号 · SoT = etf_holdings + m_pool_overrides.yaml
- **三维评分** = 弹性 35% / 性价比 30% / R:R 35%
- **12 信号** = B1-B5 买 / S1/S2a/S2b/S3 卖 / W1/W2 警 / theme_oversold_entry

## 遇问题如何处理

- **不确定某决策**：查 `core/adr.md`·没查到·提出辩论 · 让用户决是否补 ADR
- **代码与文档冲突**：代码为准·同 commit 修文档 · 在 commit message 说明
- **遇到你不能做的资源**（如凭据/SSH）：走 USER_OWNED · 让用户手动跳
- **schema 变更**：走 schema/ddl.sql + scripts/[migrate.py](http://migrate.py) · 不在业务代码 CREATE
- **daily 跑挂**：样本调起 alert 后 · verdict_text 需骨架兑底不能让 daily 崩（ADR-032）

## 文档维护责任表

| 文件 | 你动吗 | 动的时机 |
| --- | --- | --- |
| handoff/00_README_[HANDOFF.md](http://HANDOFF.md) | 可 · 避免 | 只在架构重构时动 |
| handoff/01_CONTEXT_AND_[ENV.md](http://ENV.md) | 可 | dev 环境变更时 |
| handoff/02_[STATUS.md](http://STATUS.md) | 可 | 里程碑 · patch 交付后更新 |
| handoff/03_KNOWN_[ISSUES.md](http://ISSUES.md) | 必 | 发现/修复 bug 同 commit |
| handoff/04_V5_PLUS_1_[TASKBOOK.md](http://TASKBOOK.md) | 可 | 你接手后同 commit 勾选 |
| handoff/05_CUTOVER_[REMAINING.md](http://REMAINING.md) | 可 | 收尾后歘棄或归档 |
| handoff/USER_[OWNED.md](http://OWNED.md) | 不 | 用户责任区·你仅读 |
| core/[core-logic.md](http://core-logic.md) | 必 | 业务逻辑动时同 commit |
| core/[principles.md](http://principles.md) | 可 · 避免 | 只在原则变更 · 需用户 review |
| core/[architecture.md](http://architecture.md) | 必 | schema/接口动同 commit |
| core/[stock-pool.md](http://stock-pool.md) | 可 | 池机制动时 |
| core/[adr.md](http://adr.md) | 必 | 加 ADR 追加·不修旧 |
| ops/[lightos-runtime.md](http://lightos-runtime.md) | 必 | env / cron / 路径动同 commit |
| ops/[runbook.md](http://runbook.md) | 可 | 运行事件后补充 |
| changes/*.md | 必 | 每次发版加一个 |
| reference/thesis-*.md | 可 | thesis 变动同 commit |

## 提示词·阶段 0（用户第一次贴给 codex）

```
任务：自主重构 docs/ · 暂不动业务代码。

步骤：
1. 读 docs/_raw/ 三个 source（设计权威 · 完整性基准）
2. 读 docs/handoff/00_README_HANDOFF.md 与 USER_OWNED.md
3. 读 docs/handoff/01-05 与 docs/core/ docs/ops/ docs/changes/ docs/reference/ 全部内容
4. 基于 _raw/ 检查完整性：信号阈值 / 评分公式 / 字段语义 / ADR 状态 是否齐全准确 · 哪些 _raw/ 有但 docs/ 没有
5. 自主决定 docs/ 结构：
   - 可重排子目录 · 合并相近文件 · 删冗余 · 简化标题
   - 该删的删 · 该重写的重写 · 优先 codex 视角
6. 一次 commit · message: "docs: restructure based on _raw/ source · simplify · drop redundant"
7. push origin master · 通知我 · 等我审完才进 P1

不动：
- docs/_raw/（设计快照 · 只读）
- docs/handoff/USER_OWNED.md（用户保留区）
- docs/handoff/04_V5_PLUS_1_TASKBOOK.md（V5+1 patch 清单 · 内容保留 · 结构可调）
- 业务代码 / schema/ / 配置 yaml

冲突原则：以 _raw/ 为完整性基准 · 其它可全删重写。
简化原则：能合并不分 · 能删不留 · 优先 codex 视角。
不 ssh LightOS。
```

## 提示词·阶段 1（用户审完阶段 0 后贴）

```
任务：进 P1·开始 V5+1 patch 交付。

步骤：
1. 复读 docs/handoff/04_V5_PLUS_1_TASKBOOK.md
2. 从 P1 开始·逐个 patch 交·不跳顺序·一个 patch 一个 commit
3. 同 commit 更新相关文档（详见 00 README “文档维护责任表”）
4. commit message 含 patch ID + ADR ID
5. 每个 patch 完成后通知我·我去 LightOS 跳 git pull + 部署 + 验收
6. 我验收 OK 再进下一个 patch

不 ssh LightOS·部署由我跳。
```