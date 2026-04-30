# 文档入口

本目录是 Codex 使用的 repo 侧 source of truth。Notion 可以作为阅读副本，但 Codex 随代码变更同步维护这里。

## 阅读顺序

1. `docs/README.md` - 本页：文档地图与完整性核对结果。
2. `docs/core/system.md` - 系统 SoT：业务规则、架构、字段语义、阈值、评分公式。
3. `docs/core/adr.md` - ADR 索引与当前状态。完整 ADR 正文在 `_raw/`。
4. `docs/handoff/04_V5_PLUS_1_TASKBOOK.md` - 下一阶段实现任务书。受保护，内容保留。
5. `docs/handoff/cutover.md` - 当前 cutover 状态、已知问题、用户侧命令。
6. `docs/ops/runbook.md` - LightOS 日常运维与排障。
7. `docs/reference/a-pool-thesis.md` - A 池 thesis 模板与当前 placeholder。

## 权威来源

`docs/_raw/` 是只读设计权威：

- `adr-source.md` - ADR-001 到 ADR-033 的完整背景、权衡与影响。
- `core-logic-source.md` - V4/V5 完整业务逻辑：L1-L4、A 池、评分、数据流。
- `v5.7-taskbook-source.md` - V5.7 实施计划与最新实现增量。

repo docs 与 `_raw/` 冲突时，以 `_raw/` 为准。两个 `_raw/` 文件之间出现差异时，V5.7 代码结构优先参考 implementation taskbook，旧 ADR/core 页作为设计背景保留。

## 基于 `_raw/` 的完整性核对

上一版 docs 可用但不完整。本次重构修正了这些缺口：

| 范围 | 发现的问题 | 本次处理 |
| --- | --- | --- |
| ADR 状态 | `core/adr.md` 把 ADR-018 到 ADR-033 复用成 V5.7 patch notes，和 `_raw/adr-source.md` 的真实编号冲突。 | 恢复 ADR-001 到 ADR-033 的 canonical index。V5.7 变化改写成 implementation notes，不再伪造 ADR 编号。 |
| 信号阈值 | 短文档漏掉 L1 S 档硬门槛、L2 分位窗口、L3 象限映射、主题量能双控。 | 合并进 `core/system.md`，保留具体阈值与公式。 |
| 评分公式 | A 池评分只写了摘要，缺少子权重和战略/战术 R:R 拆分。 | 补全 A_Score、子权重、过滤、加分和扣分。 |
| 字段语义 | `a_pool.yaml` 的 status、mcap 字段、DB 镜像边界在多个文件中不一致。 | `core/system.md` 明确 YAML 是 SoT；DB 仅镜像 `pool` / `is_active` / `thesis_added_at`。 |
| 日报输出 | 旧 docs 仍混有 NAV / 模拟盘日报段。 | 按 ADR-033 明确日报不含 NAV 和模拟盘仓位；backtest 仅本地 CLI。 |
| M 池 universe | 有些文档使用较弱过滤条件，如 `ADV > 1M`、上市 1 年。 | 恢复 `_raw` 标准：市值 >= $1B、20D dollar volume >= $10M、`ipoDate >= 90d`、`actively_trading=true`。 |

## 简化后的结构

```text
docs/
├── README.md
├── _raw/                         # 只读设计快照
├── core/
│   ├── system.md                 # 业务逻辑 + 架构 + 字段语义合并页
│   └── adr.md                    # canonical ADR 索引
├── handoff/
│   ├── 00_README_HANDOFF.md      # 极简入口
│   ├── 04_V5_PLUS_1_TASKBOOK.md  # 受保护任务书
│   ├── USER_OWNED.md             # 受保护用户边界
│   └── cutover.md                # 由旧 01/02/03/05 合并
├── ops/
│   └── runbook.md
├── changes/
│   └── 2026-04-V5.7.md
├── codex-deliveries/              # 历史交付收据，不在主动阅读链
└── reference/
    └── a-pool-thesis.md
```

## 边界

- 不编辑 `_raw/`。
- 不编辑 `handoff/USER_OWNED.md`，除非用户明确要求。
- `handoff/04_V5_PLUS_1_TASKBOOK.md` 内容保留；需要时只改路径引用或周边结构。
- Codex 不 SSH LightOS。部署命令由用户跑。
- docs-only 任务不碰业务代码、`schema/` 或 yaml 配置。
