-- migration: M3-S1 PR3-A
-- desc: Create L1 regime and L2 breadth signal output tables.
-- created: 2026-04-29
-- depends_on: 003_create_daily_indicators.sql

CREATE TABLE IF NOT EXISTS signals_daily (
    trade_date DATE NOT NULL,
    regime CHAR(1) NOT NULL CHECK (regime IN ('S','A','B','C','D')),
    regime_streak INT NOT NULL DEFAULT 0,
    regime_prev CHAR(1),
    regime_changed BOOLEAN NOT NULL DEFAULT FALSE,
    breadth_pct_above_200ma NUMERIC(5,2),
    breadth_pct_above_50ma NUMERIC(5,2),
    breadth_pct_above_20ma NUMERIC(5,2),
    breadth_nh_nl_ratio NUMERIC(8,2),
    breadth_mcclellan NUMERIC(8,2),
    breadth_pct_above_200ma_p5y NUMERIC(5,2),
    breadth_pct_above_50ma_p5y NUMERIC(5,2),
    breadth_pct_above_50ma_p2y NUMERIC(5,2),
    breadth_score INT,
    sectors_top3 JSONB,
    sectors_quadrant JSONB,
    themes_top3 JSONB,
    as_of_date DATE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (trade_date)
);

CREATE INDEX IF NOT EXISTS idx_sd_regime ON signals_daily(regime);
CREATE INDEX IF NOT EXISTS idx_sd_as_of ON signals_daily(as_of_date);

CREATE TABLE IF NOT EXISTS signals_alerts (
    id BIGSERIAL PRIMARY KEY,
    trade_date DATE NOT NULL,
    alert_type TEXT NOT NULL CHECK (alert_type IN (
        'NH_NL_EXTREME',
        'MCCLELLAN_EXTREME',
        'ZWEIG_BREADTH_THRUST',
        'BREADTH_50MA_EXTREME',
        'BREADTH_200MA_LOW',
        'BREADTH_TOP_DIVERGENCE'
    )),
    severity TEXT NOT NULL CHECK (severity IN ('YELLOW','RED')),
    detail JSONB NOT NULL,
    as_of_date DATE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (trade_date, alert_type, severity)
);

CREATE INDEX IF NOT EXISTS idx_sa_date ON signals_alerts(trade_date);
CREATE INDEX IF NOT EXISTS idx_sa_type ON signals_alerts(alert_type);
