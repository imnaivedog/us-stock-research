# ADR Index

Canonical numbering follows `docs/_raw/adr-source.md`. Do not reuse ADR IDs for implementation notes. If code introduces a new architectural decision, append a new ADR ID after ADR-033 or mark an older ADR as superseded.

## Status Vocabulary

- **Accepted**: current design constraint.
- **Superseded**: replaced or materially narrowed by a later ADR or V5.7 implementation delta.
- **Implementation Delta**: `_raw/v5.7-taskbook-source.md` changed implementation shape without creating a new canonical ADR.
- **Deprecated**: explicitly abandoned.
- **Open**: reserved/future question.

## Canonical ADRs

| ADR | Decision | Current status |
| --- | --- | --- |
| ADR-001 | Four-layer L1-L4 system and layer semantics. L3 is observation only; L4 is execution. | Accepted |
| ADR-002 | Stock universe = SP Composite 1500 + QQQ foreign/ADR additions + IPO/Hermes/manual supplements. | Superseded in implementation by ADR-022/023/025 and V5.7 m_pool curation details |
| ADR-003 | Macro section renamed to macro regime; 8 macro scenarios. | Accepted |
| ADR-004 | Dial S/A/B/C/D with positions 120/100/80/60/20. | Accepted |
| ADR-005 | 50/30/20 staged entry. | Accepted for backtest/local simulator |
| ADR-006 | R-multiple staged take profit. | Accepted for backtest/local simulator |
| ADR-007 | Two simulated pools, ETF and stock. | Superseded by ADR-033 for cloud daily output; retained for local backtest |
| ADR-008 | Differentiated percentile windows instead of all-5Y. | Accepted |
| ADR-009 | Theme volume uses 1Y percentile plus absolute volume control. | Accepted |
| ADR-010 | BTC joins macro confirmation as risk-on/off input, not a standalone scenario. | Accepted |
| ADR-011 | Simulated-trading daily section simplified. | Superseded by ADR-033; daily now excludes simulated trading |
| ADR-012 | Notion full report and Discord brief split. | Accepted, with ADR-033 removing NAV/report tracking pieces |
| ADR-013 | Split bloated Notion page into focused pages. | Superseded by repo docs structure; source remains historical context |
| ADR-014 | Simulation start moved to 2025-01-01 due to FMP Starter 5Y window. | Accepted for backtest |
| ADR-015 | S dial quantitative trigger: 4 hard gates + 1 momentum + 3 days. | Accepted |
| ADR-016 | L3 sector quadrant mapping by relative rank plus absolute percentile floor. | Accepted |
| ADR-017 | Simulator single-direction flow and live/backtest isolation; algorithm must not read simulator state. | Accepted; Cloud SQL/live parts adapted by V5.7 deployment |
| ADR-018 | Daily idempotency and `trade_id` uniqueness. | Superseded by ADR-033 for cloud daily trade tracking; retained for local backtest/report idempotency |
| ADR-019 | Seven-exit trigger priority; 5D minimum hold constrains only active rotation. | Retained for local backtest |
| ADR-020 | Asymmetric dial cooldown. | Accepted |
| ADR-021 | Notion row properties + page body persistence. | Accepted but simplified by ADR-033: no NAV fields/section |
| ADR-022 | M pool source via FMP ETF holdings. | Accepted as source principle; V5.7 curation implements via repo package |
| ADR-023 | M pool quality hard filters. | Accepted: market cap >= $1B, 20D dollar volume >= $10M, ipoDate >= 90d, actively trading |
| ADR-024 | Notion output-only and one-way data flow. | Accepted |
| ADR-025 | Dynamic member management: monthly local diff, soft retirement, dedupe priority. | Accepted |
| ADR-026 | Bootstrap / Curation / Operate deployment split. | Accepted; V5.7 runs current production on LightOS instead of the older Cloud Run-only shape |
| ADR-027 | Cloud SQL Postgres + GCS/bootstrap + local backtest SQLite. | Implementation Delta: V5.7 production runtime is LightOS Postgres 17; Postgres remains accepted data-store choice |
| ADR-028 | `themes.yaml` seed strategy: ETF reverse inference plus user review. | Accepted |
| ADR-029 | Watchlist side table for social/thesis collaboration. | Implementation Delta: current A pool thesis SoT is `config/a_pool.yaml`; watchlist remains conceptually separate, not a trading position |
| ADR-030 | A pool long-thesis timing as parallel sidecar. | Accepted; V5.7 extends original 11 signals to 12 with `theme_oversold_entry` |
| ADR-031 | `daily_indicators` table and compute job. | Accepted |
| ADR-032 | M pool L1-L4 + macro signal engine in 5 modules. | Accepted |
| ADR-033 | Cloud ETL/local BI split; simulated trading removed from daily report and moved to local CLI. | Accepted and currently decisive for reports/backtest boundary |

## Rejected Or Deprecated Proposals

From `_raw/adr-source.md`:

| ID | Proposal | Status |
| --- | --- | --- |
| X-01 | Real-position breakdown warning section in this system. | Deprecated |
| X-02 | No explicit take-profit, only exit on breakdown. | Deprecated by ADR-006 |
| X-03 | Future Phase 5 position-monitoring system inside this repo. | Deprecated |
| X-04 | Macro indicators directly enter algorithm. | Deprecated; macro is context/reference |
| X-05 | 20MA breadth direction arrow in main judgment. | Deprecated |
| X-06 | L3 sector directly creates stock operations. | Deprecated by ADR-001 |

## V5.7 Implementation Notes

These are implementation deltas from `_raw/v5.7-taskbook-source.md`, not canonical ADR IDs:

- Monorepo is three main packages plus MCP: data, analytics, reports, MCP.
- `config/a_pool.yaml` is A pool SoT; core thesis fields are not mirrored into DB.
- A pool mcap anchors are `thesis_stop_mcap_b` and `target_mcap_b`; prices are derived from `shares_outstanding`.
- A pool signal set is 12 classes: B1-B5, S1/S2a/S2b/S3, W1/W2, `theme_oversold_entry`.
- A pool scoring uses 35/30/35 elasticity/value/R:R with explicit subweights in `system.md`.
- MCP tools are capped at 4 read-only tools: `get_dial`, `get_top_themes`, `get_top_stocks`, `query_signals`.
- `verdict_text` must have a deterministic fallback so LLM failure never breaks daily.

## Codex Rules

1. Before code changes, check this index and `system.md`.
2. If a code change relies on an ADR, mention the ADR number in the commit or final note.
3. If a decision conflicts with an ADR, ask the user before implementing and add/supersede an ADR in the same commit.
4. Do not silently create "new ADR-018"-style local numbering again. That caused drift.
