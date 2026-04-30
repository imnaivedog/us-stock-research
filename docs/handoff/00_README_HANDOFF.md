# Handoff Entry

Start at `docs/README.md`. This file is intentionally short so there is only one real docs entry point.

Current phase:

- Stage 0 docs restructure: done in this commit, pending user review.
- Do not start P1 until the user approves the docs restructure.
- P1 source: `docs/handoff/04_V5_PLUS_1_TASKBOOK.md`.
- Cutover state and remaining commands: `docs/handoff/cutover.md`.
- User-owned boundaries: `docs/handoff/USER_OWNED.md`.

Non-negotiables:

- `_raw/` stays read-only.
- `USER_OWNED.md` stays user-owned.
- Codex does not SSH to LightOS.
- Code changes must update docs in the same commit when behavior changes.
