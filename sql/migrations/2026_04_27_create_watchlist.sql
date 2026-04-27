-- migrate:up
CREATE TABLE watchlist (
    symbol VARCHAR PRIMARY KEY REFERENCES symbol_universe(symbol),
    source VARCHAR NOT NULL,
    added_date DATE NOT NULL,
    sector VARCHAR,
    target_market_cap NUMERIC,
    status VARCHAR NOT NULL CHECK (
        status IN ('watching','researching','thesis_ready','held','exited','rejected')
    ),
    thesis_url VARCHAR,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_watchlist_status ON watchlist(status);
CREATE INDEX idx_watchlist_sector ON watchlist(sector);

-- migrate:down
DROP TABLE IF EXISTS watchlist;
