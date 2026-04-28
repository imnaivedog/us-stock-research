-- migration: M3-S1 PR2
-- desc: Create daily_indicators table for computed technical indicator snapshots.
-- created: 2026-04-29
-- depends_on: quotes_daily

CREATE TABLE IF NOT EXISTS daily_indicators (
    symbol VARCHAR NOT NULL,
    trade_date DATE NOT NULL,
    sma_5 NUMERIC,
    sma_10 NUMERIC,
    sma_20 NUMERIC,
    sma_50 NUMERIC,
    sma_200 NUMERIC,
    ema_12 NUMERIC,
    ema_26 NUMERIC,
    macd_line NUMERIC,
    macd_signal NUMERIC,
    macd_histogram NUMERIC,
    bb_upper NUMERIC,
    bb_middle NUMERIC,
    bb_lower NUMERIC,
    bb_width NUMERIC,
    rsi_14 NUMERIC,
    obv BIGINT,
    vwap_20 NUMERIC,
    atr_14 NUMERIC,
    std_20 NUMERIC,
    std_60 NUMERIC,
    adx_14 NUMERIC,
    di_plus_14 NUMERIC,
    di_minus_14 NUMERIC,
    pct_to_52w_high NUMERIC,
    pct_to_52w_low NUMERIC,
    pct_to_200ma NUMERIC,
    beta_60d NUMERIC,
    ma200_slope_20d NUMERIC,
    computed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (symbol, trade_date)
);

CREATE INDEX IF NOT EXISTS idx_di_date ON daily_indicators(trade_date);
CREATE INDEX IF NOT EXISTS idx_di_symbol ON daily_indicators(symbol);
