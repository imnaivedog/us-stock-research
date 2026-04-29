-- migration: M3-S1 PR3
-- desc: Add simple macro state output to signals_daily.
-- created: 2026-04-29
-- depends_on: 005_extend_signals_for_l3_l4.sql

ALTER TABLE signals_daily
    ADD COLUMN IF NOT EXISTS macro_state TEXT
    CHECK (macro_state IN ('risk_on', 'risk_off', 'neutral'));

CREATE INDEX IF NOT EXISTS idx_sd_macro_state ON signals_daily(macro_state);
