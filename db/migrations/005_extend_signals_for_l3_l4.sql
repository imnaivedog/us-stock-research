-- migration: M3-S1 PR3-B
-- desc: Add L3 sector, L4 theme, and L4 stock signal detail tables.
-- created: 2026-04-29
-- depends_on: 004_create_signals_l1_l2.sql

CREATE TABLE IF NOT EXISTS signals_sectors_daily (
    trade_date DATE NOT NULL,
    symbol TEXT NOT NULL,
    score_trend NUMERIC(5,2),
    score_rs NUMERIC(5,2),
    score_breadth NUMERIC(5,2),
    score_money_flow NUMERIC(5,2),
    score_volatility NUMERIC(5,2),
    total_score NUMERIC(5,2),
    rank_relative INT,
    pct_5y NUMERIC(5,2),
    quadrant TEXT NOT NULL CHECK (quadrant IN ('LEADING','STRONG','NEUTRAL','WEAK','LAGGING')),
    multiplier NUMERIC(4,3) NOT NULL,
    as_of_date DATE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (trade_date, symbol)
);

CREATE TABLE IF NOT EXISTS signals_themes_daily (
    trade_date DATE NOT NULL,
    theme_id TEXT NOT NULL,
    theme_name TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('INCUBATING','LAUNCHING','ACCELERATING','DECAYING')),
    rank INT,
    total_score NUMERIC(5,2),
    volume_ratio_3m NUMERIC(5,2),
    volume_pct_1y NUMERIC(5,2),
    volume_alert TEXT CHECK (volume_alert IN ('NONE','YELLOW','RED','SAMPLE_INSUFFICIENT')),
    core_avg_change_pct NUMERIC(6,2),
    diffusion_avg_change_pct NUMERIC(6,2),
    as_of_date DATE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (trade_date, theme_id)
);

CREATE TABLE IF NOT EXISTS signals_stocks_daily (
    trade_date DATE NOT NULL,
    symbol TEXT NOT NULL,
    total_score NUMERIC(5,2),
    technical_score NUMERIC(5,2),
    fundamental_score NUMERIC(5,2),
    theme_bonus NUMERIC(5,2),
    sector_multiplier NUMERIC(4,3),
    rank INT,
    is_top5 BOOLEAN NOT NULL DEFAULT FALSE,
    entry_pattern TEXT CHECK (entry_pattern IN ('BREAKOUT','PULLBACK','EVENT')),
    primary_sector TEXT,
    primary_theme TEXT,
    as_of_date DATE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (trade_date, symbol)
);

CREATE INDEX IF NOT EXISTS idx_ssd_score ON signals_sectors_daily(trade_date, total_score DESC);
CREATE INDEX IF NOT EXISTS idx_std_score ON signals_themes_daily(trade_date, total_score DESC);
CREATE INDEX IF NOT EXISTS idx_sstd_top ON signals_stocks_daily(trade_date, is_top5);
