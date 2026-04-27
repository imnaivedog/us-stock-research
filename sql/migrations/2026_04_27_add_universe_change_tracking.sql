-- migrate:up
BEGIN;

ALTER TABLE symbol_universe
    ADD COLUMN IF NOT EXISTS first_seen DATE,
    ADD COLUMN IF NOT EXISTS last_seen DATE;

UPDATE symbol_universe
SET first_seen = COALESCE(first_seen, added_date, as_of_date, CURRENT_DATE)
WHERE is_active IS TRUE;

UPDATE symbol_universe
SET last_seen = COALESCE(last_seen, removed_date, last_seen_date, CURRENT_DATE)
WHERE is_active IS NOT TRUE;

UPDATE symbol_universe
SET last_seen = NULL
WHERE is_active IS TRUE;

CREATE INDEX IF NOT EXISTS idx_su_active ON symbol_universe(is_active);
CREATE INDEX IF NOT EXISTS idx_su_last_seen ON symbol_universe(last_seen);

CREATE TABLE IF NOT EXISTS symbol_universe_changes (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR NOT NULL REFERENCES symbol_universe(symbol),
    change_date DATE NOT NULL DEFAULT CURRENT_DATE,
    change_type VARCHAR NOT NULL CHECK (change_type IN ('added','removed','forced_in')),
    reason VARCHAR,
    market_cap NUMERIC,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_suc_symbol ON symbol_universe_changes(symbol);
CREATE INDEX IF NOT EXISTS idx_suc_date ON symbol_universe_changes(change_date);

COMMIT;

-- migrate:down
BEGIN;

DROP INDEX IF EXISTS idx_suc_date;
DROP INDEX IF EXISTS idx_suc_symbol;
DROP TABLE IF EXISTS symbol_universe_changes;
DROP INDEX IF EXISTS idx_su_last_seen;
DROP INDEX IF EXISTS idx_su_active;

ALTER TABLE symbol_universe
    DROP COLUMN IF EXISTS last_seen,
    DROP COLUMN IF EXISTS first_seen;

COMMIT;
