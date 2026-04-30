-- migration: M3-S1 PR1
-- desc: Create A-pool calibration and daily signal tables physically isolated from M-pool tables.
-- created: 2026-04-28
-- depends_on: 001_signals_m_pool.sql

CREATE TABLE IF NOT EXISTS a_pool_calibration (
    symbol VARCHAR(10) PRIMARY KEY,
    typical_pullback_pct NUMERIC(5,2),
    deep_pullback_pct NUMERIC(5,2),
    extreme_pullback_pct NUMERIC(5,2),
    strong_supports JSONB,
    strong_resistances JSONB,
    rsi_low_5pct NUMERIC(5,2),
    rsi_high_95pct NUMERIC(5,2),
    typical_uptrend_days INTEGER,
    typical_uptrend_gain_pct NUMERIC(5,2),
    atr_pct_median NUMERIC(5,2),
    atr_pct_p70 NUMERIC(5,2),
    beta_60d NUMERIC(5,2),
    beta_stability NUMERIC(5,2),
    sigma_20d_median NUMERIC(5,2),
    data_window_start DATE,
    data_window_end DATE,
    calibrated_at TIMESTAMPTZ,
    notes JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE a_pool_calibration IS 'A-pool per-symbol historical calibration profile, refreshed weekly.';
COMMENT ON COLUMN a_pool_calibration.symbol IS 'A-pool ticker symbol.';
COMMENT ON COLUMN a_pool_calibration.typical_pullback_pct IS 'Typical pullback depth, usually median historical pullback percent.';
COMMENT ON COLUMN a_pool_calibration.deep_pullback_pct IS 'Deep pullback depth, usually 75th percentile historical pullback percent.';
COMMENT ON COLUMN a_pool_calibration.extreme_pullback_pct IS 'Extreme pullback depth, usually 95th percentile historical pullback percent.';
COMMENT ON COLUMN a_pool_calibration.strong_supports IS 'Strong support levels as JSON array, e.g. [{price, hits, last_test_date, type}].';
COMMENT ON COLUMN a_pool_calibration.strong_resistances IS 'Strong resistance levels using the same structure as strong_supports.';
COMMENT ON COLUMN a_pool_calibration.rsi_low_5pct IS 'Historical RSI 5th percentile used as oversold reference.';
COMMENT ON COLUMN a_pool_calibration.rsi_high_95pct IS 'Historical RSI 95th percentile used as overheated reference.';
COMMENT ON COLUMN a_pool_calibration.typical_uptrend_days IS 'Typical duration of an uptrend in trading days.';
COMMENT ON COLUMN a_pool_calibration.typical_uptrend_gain_pct IS 'Typical gain during an uptrend, percent.';
COMMENT ON COLUMN a_pool_calibration.atr_pct_median IS 'Median ATR percent used for elasticity reference.';
COMMENT ON COLUMN a_pool_calibration.atr_pct_p70 IS '70th percentile ATR percent used for cross-sectional scoring.';
COMMENT ON COLUMN a_pool_calibration.beta_60d IS '60-day beta.';
COMMENT ON COLUMN a_pool_calibration.beta_stability IS 'Beta stability score from 0 to 1, where 1 means stable.';
COMMENT ON COLUMN a_pool_calibration.sigma_20d_median IS 'Median 20-day volatility sigma percent.';
COMMENT ON COLUMN a_pool_calibration.data_window_start IS 'Start date of the historical data window used for calibration.';
COMMENT ON COLUMN a_pool_calibration.data_window_end IS 'End date of the historical data window used for calibration.';
COMMENT ON COLUMN a_pool_calibration.calibrated_at IS 'Timestamp when this calibration profile was generated.';
COMMENT ON COLUMN a_pool_calibration.notes IS 'Free-form diagnostics or manual notes for calibration.';
COMMENT ON COLUMN a_pool_calibration.created_at IS 'Row creation timestamp.';
COMMENT ON COLUMN a_pool_calibration.updated_at IS 'Application-maintained row update timestamp.';

CREATE INDEX IF NOT EXISTS idx_a_pool_calibration_calibrated_at ON a_pool_calibration (calibrated_at DESC);

CREATE TABLE IF NOT EXISTS signals_a_pool_daily (
    trade_date DATE NOT NULL,
    symbol VARCHAR(10) NOT NULL,
    thesis_status VARCHAR(20),
    thesis_age_months INTEGER,
    close NUMERIC(10,2),
    chg_pct NUMERIC(6,2),
    dist_50ma_pct NUMERIC(6,2),
    dist_200ma_pct NUMERIC(6,2),
    dist_52w_high_pct NUMERIC(6,2),
    dist_52w_low_pct NUMERIC(6,2),
    rsi_14 NUMERIC(5,2),
    atr_pct NUMERIC(5,2),
    position_temp VARCHAR(10),
    buy_signals_json JSONB,
    sell_signals_json JSONB,
    warning_signals_json JSONB,
    entry_aggressive NUMERIC(10,2),
    entry_conservative NUMERIC(10,2),
    entry_extreme NUMERIC(10,2),
    stop_shallow NUMERIC(10,2),
    stop_deep NUMERIC(10,2),
    target_short NUMERIC(10,2),
    elasticity_score NUMERIC(5,2),
    value_score NUMERIC(5,2),
    rr_score NUMERIC(5,2),
    a_score NUMERIC(5,2),
    filter_pass BOOLEAN DEFAULT FALSE,
    filter_f1_liquidity BOOLEAN,
    filter_f2_no_gap BOOLEAN,
    filter_f3_consistency BOOLEAN,
    filter_notes JSONB,
    verdict_text TEXT,
    verdict_action_hint VARCHAR(20),
    llm_filled_at TIMESTAMPTZ,
    llm_model VARCHAR(40),
    notes JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (trade_date, symbol)
);

COMMENT ON TABLE signals_a_pool_daily IS 'A-pool daily signals for watchlist thesis candidates, physically isolated from M-pool signal tables.';
COMMENT ON COLUMN signals_a_pool_daily.trade_date IS 'US Eastern market close date for this A-pool signal row.';
COMMENT ON COLUMN signals_a_pool_daily.symbol IS 'A-pool ticker symbol.';
COMMENT ON COLUMN signals_a_pool_daily.thesis_status IS 'Thesis status: active, pending, or sunset.';
COMMENT ON COLUMN signals_a_pool_daily.thesis_age_months IS 'Age of the thesis in months, used by W2 aging logic.';
COMMENT ON COLUMN signals_a_pool_daily.close IS 'Stock close price.';
COMMENT ON COLUMN signals_a_pool_daily.chg_pct IS 'Stock daily percentage change.';
COMMENT ON COLUMN signals_a_pool_daily.dist_50ma_pct IS 'Distance from 50-day moving average, percent.';
COMMENT ON COLUMN signals_a_pool_daily.dist_200ma_pct IS 'Distance from 200-day moving average, percent.';
COMMENT ON COLUMN signals_a_pool_daily.dist_52w_high_pct IS 'Distance from 52-week high, percent.';
COMMENT ON COLUMN signals_a_pool_daily.dist_52w_low_pct IS 'Distance from 52-week low, percent.';
COMMENT ON COLUMN signals_a_pool_daily.rsi_14 IS '14-day RSI.';
COMMENT ON COLUMN signals_a_pool_daily.atr_pct IS 'ATR as percent of close.';
COMMENT ON COLUMN signals_a_pool_daily.position_temp IS 'Position temperature: cold, cool, warm, hot, or overheated.';
COMMENT ON COLUMN signals_a_pool_daily.buy_signals_json IS 'Buy signals B1-B5 with confidence, historical reference, and explanation.';
COMMENT ON COLUMN signals_a_pool_daily.sell_signals_json IS 'Sell signals S1-S3 with details.';
COMMENT ON COLUMN signals_a_pool_daily.warning_signals_json IS 'Warning signals W1-W2 with details.';
COMMENT ON COLUMN signals_a_pool_daily.entry_aggressive IS 'Aggressive entry level based on typical shallow pullback.';
COMMENT ON COLUMN signals_a_pool_daily.entry_conservative IS 'Conservative entry level based on deep pullback.';
COMMENT ON COLUMN signals_a_pool_daily.entry_extreme IS 'Extreme entry level based on extreme pullback.';
COMMENT ON COLUMN signals_a_pool_daily.stop_shallow IS 'Shallow tactical stop level.';
COMMENT ON COLUMN signals_a_pool_daily.stop_deep IS 'Deep thesis-break stop level.';
COMMENT ON COLUMN signals_a_pool_daily.target_short IS 'Short-term target price.';
COMMENT ON COLUMN signals_a_pool_daily.elasticity_score IS 'Elasticity score from 0 to 100.';
COMMENT ON COLUMN signals_a_pool_daily.value_score IS 'Value score from 0 to 100.';
COMMENT ON COLUMN signals_a_pool_daily.rr_score IS 'Risk-reward score from 0 to 100.';
COMMENT ON COLUMN signals_a_pool_daily.a_score IS 'Composite A-pool score from 0 to 100.';
COMMENT ON COLUMN signals_a_pool_daily.filter_pass IS 'Whether all three filters passed.';
COMMENT ON COLUMN signals_a_pool_daily.filter_f1_liquidity IS 'F1 liquidity filter: ADV20 at least $10M.';
COMMENT ON COLUMN signals_a_pool_daily.filter_f2_no_gap IS 'F2 gap filter: no plus/minus 15 percent gap in recent 5 days.';
COMMENT ON COLUMN signals_a_pool_daily.filter_f3_consistency IS 'F3 consistency filter for three-dimensional score alignment.';
COMMENT ON COLUMN signals_a_pool_daily.filter_notes IS 'Filter diagnostics and explanations.';
COMMENT ON COLUMN signals_a_pool_daily.verdict_text IS 'Plain-language LLM verdict, filled by a later PR.';
COMMENT ON COLUMN signals_a_pool_daily.verdict_action_hint IS 'LLM action hint such as add, hold, alert, sell, or watch.';
COMMENT ON COLUMN signals_a_pool_daily.llm_filled_at IS 'Timestamp when LLM verdict fields were filled; NULL means not filled.';
COMMENT ON COLUMN signals_a_pool_daily.llm_model IS 'LLM model used for verdict fields.';
COMMENT ON COLUMN signals_a_pool_daily.notes IS 'Free-form diagnostics or manual notes for A-pool daily signals.';
COMMENT ON COLUMN signals_a_pool_daily.created_at IS 'Row creation timestamp.';
COMMENT ON COLUMN signals_a_pool_daily.updated_at IS 'Application-maintained row update timestamp.';

CREATE INDEX IF NOT EXISTS idx_signals_a_pool_daily_symbol_date ON signals_a_pool_daily (symbol, trade_date DESC);
CREATE INDEX IF NOT EXISTS idx_signals_a_pool_daily_trade_date_score ON signals_a_pool_daily (trade_date, a_score DESC);
CREATE INDEX IF NOT EXISTS idx_signals_a_pool_daily_filter_pass ON signals_a_pool_daily (trade_date) WHERE filter_pass = TRUE;
