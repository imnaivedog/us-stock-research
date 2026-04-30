# Docs Entry

This directory is the repo-side source of truth for Codex. Notion may mirror some pages for reading, but Codex updates this tree with code changes.

## Read Order

1. `docs/README.md` - this file: source map and integrity notes.
2. `docs/core/system.md` - business rules, architecture, fields, thresholds, scoring.
3. `docs/core/adr.md` - ADR index and current status. Full ADR text lives in `_raw/`.
4. `docs/handoff/04_V5_PLUS_1_TASKBOOK.md` - next implementation taskbook. Protected content.
5. `docs/handoff/cutover.md` - current cutover state, known issues, user-side commands.
6. `docs/ops/runbook.md` - recurring LightOS operations and triage.
7. `docs/reference/a-pool-thesis.md` - thesis template and current placeholders.

## Source Authority

`docs/_raw/` is read-only design authority:

- `adr-source.md` - full ADR-001 to ADR-033 with context and tradeoffs.
- `core-logic-source.md` - full V4/V5 business logic: L1-L4, A pool, scoring, data flow.
- `v5.7-taskbook-source.md` - V5.7 implementation plan and the latest implementation deltas.

When repo docs conflict with `_raw/`, `_raw/` wins. When two `_raw/` files differ, prefer the later implementation-specific taskbook for V5.7 code shape and keep the older ADR/core page as design background.

## Integrity Audit From `_raw/`

The previous docs were useful but incomplete. This restructure fixes the following gaps:

| Area | Gap found | Resolution |
| --- | --- | --- |
| ADR status | `core/adr.md` reused ADR-018 to ADR-033 for V5.7 patch notes, conflicting with real `_raw/adr-source.md` numbering. | Restored ADR-001 to ADR-033 as the canonical index. V5.7 changes are now implementation notes, not new ADR numbers. |
| Signal thresholds | Short docs omitted L1 S hard gates, L2 percentile windows, L3 quadrant mapping, theme volume controls. | Consolidated into `core/system.md` with exact thresholds and formulas. |
| Scoring formulas | A pool scoring was summarized but missing subweights and strategic/tactical R:R split. | Added full A_Score formula, subweights, filters, bonuses, and penalties. |
| Field semantics | `a_pool.yaml` status values and mcap fields differed across docs; some pages implied DB mirrors thesis fields. | `core/system.md` now states YAML is SoT, DB mirrors only `pool` / `is_active` / `thesis_added_at`, and mcap fields stay out of DB. |
| Daily output | Older docs still described NAV / simulated portfolio in daily report. | ADR-033 is now explicit: daily report excludes NAV and simulated-pool sections; backtest is local CLI. |
| M pool universe | Some docs used weaker filters (`ADV > 1M`, listed >1y) than `_raw` V5.7 source. | Restored `_raw` filters: market cap >= $1B, 20D dollar volume >= $10M, ipoDate >= 90d, actively_trading=true. |

## Simplified Structure

```
docs/
├── README.md
├── _raw/                         # read-only source snapshots
├── core/
│   ├── system.md                 # merged logic + architecture + fields
│   └── adr.md                    # canonical ADR index
├── handoff/
│   ├── 00_README_HANDOFF.md      # short redirect
│   ├── 04_V5_PLUS_1_TASKBOOK.md  # protected taskbook
│   ├── USER_OWNED.md             # protected user-owned boundary
│   └── cutover.md                # merged 01/02/03/05
├── ops/
│   └── runbook.md
├── changes/
│   └── 2026-04-V5.7.md
├── codex-deliveries/              # legacy delivery receipts, not active read order
└── reference/
    └── a-pool-thesis.md
```

## Boundaries

- Do not edit `_raw/`.
- Do not edit `handoff/USER_OWNED.md` unless the user explicitly asks.
- Preserve the content of `handoff/04_V5_PLUS_1_TASKBOOK.md`; update only around it if needed.
- Do not SSH to LightOS. User runs deployment commands.
- Do not touch business code, `schema/`, or YAML config in docs-only work.
