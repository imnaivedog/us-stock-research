-- migration: M3-S1 PR1
-- desc: Create M-pool daily signal tables for market, sector, theme, and stock outputs.
-- created: 2026-04-28
-- depends_on: 无

CREATE TABLE IF NOT EXISTS signals_daily (
    trade_date DATE NOT NULL,
    regime VARCHAR(20),
    spx_close NUMERIC(10,2),
    spx_chg_pct NUMERIC(6,2),
    spx_dist_50ma_pct NUMERIC(6,2),
    spx_dist_200ma_pct NUMERIC(6,2),
    vix NUMERIC(6,2),
    breadth_advance_pct NUMERIC(5,2),
    breadth_above_50ma_pct NUMERIC(5,2),
    breadth_above_200ma_pct NUMERIC(5,2),
    triggers_hit JSONB,
    chain_details JSONB,
    daily_grade VARCHAR(10),
    grade_stable_days INTEGER,
    prev_grade VARCHAR(10),
    regime_changed BOOLEAN DEFAULT FALSE,
    layer1_flag BOOLEAN DEFAULT FALSE,
    layer2_flag BOOLEAN DEFAULT FALSE,
    notes JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (trade_date)
);

COMMENT ON TABLE signals_daily IS 'M-pool market-level daily signal row: L1 regime, L2 breadth, and macro context.';
COMMENT ON COLUMN signals_daily.trade_date IS 'US Eastern market close date for this signal row.';
COMMENT ON COLUMN signals_daily.regime IS 'Market regime: bull, bear, range, or transition.';
COMMENT ON COLUMN signals_daily.spx_close IS 'S&P 500 close price.';
COMMENT ON COLUMN signals_daily.spx_chg_pct IS 'S&P 500 daily percentage change.';
COMMENT ON COLUMN signals_daily.spx_dist_50ma_pct IS 'S&P 500 distance from 50-day moving average, percent.';
COMMENT ON COLUMN signals_daily.spx_dist_200ma_pct IS 'S&P 500 distance from 200-day moving average, percent.';
COMMENT ON COLUMN signals_daily.vix IS 'VIX level for the trade date.';
COMMENT ON COLUMN signals_daily.breadth_advance_pct IS 'Percent of active universe advancing on the trade date.';
COMMENT ON COLUMN signals_daily.breadth_above_50ma_pct IS 'Percent of active universe above 50-day moving average.';
COMMENT ON COLUMN signals_daily.breadth_above_200ma_pct IS 'Percent of active universe above 200-day moving average.';
COMMENT ON COLUMN signals_daily.triggers_hit IS 'Market trigger hits, e.g. bull_break, bear_break, momentum_cross, squeeze_release, vol_spike, breadth_flip, regime_shift.';
COMMENT ON COLUMN signals_daily.chain_details IS 'Detailed parameters and evidence for each market signal chain.';
COMMENT ON COLUMN signals_daily.daily_grade IS 'Daily market grade: S, A, B, C, or D.';
COMMENT ON COLUMN signals_daily.grade_stable_days IS 'Consecutive days the current market grade has persisted.';
COMMENT ON COLUMN signals_daily.prev_grade IS 'Previous market grade before the current trade date.';
COMMENT ON COLUMN signals_daily.regime_changed IS 'Whether the market regime changed on this trade date.';
COMMENT ON COLUMN signals_daily.layer1_flag IS 'Whether this row should appear in the required first-layer daily report.';
COMMENT ON COLUMN signals_daily.layer2_flag IS 'Whether this row should appear in the deeper second-layer daily report.';
COMMENT ON COLUMN signals_daily.notes IS 'Free-form diagnostics or manual notes for market signals.';
COMMENT ON COLUMN signals_daily.created_at IS 'Row creation timestamp.';
COMMENT ON COLUMN signals_daily.updated_at IS 'Application-maintained row update timestamp.';

CREATE INDEX IF NOT EXISTS idx_signals_daily_regime ON signals_daily (regime);
CREATE INDEX IF NOT EXISTS idx_signals_daily_daily_grade ON signals_daily (daily_grade);

CREATE TABLE IF NOT EXISTS signals_sector_daily (
    trade_date DATE NOT NULL,
    sector_code VARCHAR(20) NOT NULL,
    sector_name VARCHAR(60),
    sector_chg_pct NUMERIC(6,2),
    relative_strength NUMERIC(6,2),
    breadth_above_50ma_pct NUMERIC(5,2),
    top_movers JSONB,
    triggers_hit JSONB,
    chain_details JSONB,
    sector_grade VARCHAR(10),
    grade_stable_days INTEGER,
    prev_grade VARCHAR(10),
    layer1_flag BOOLEAN DEFAULT FALSE,
    layer2_flag BOOLEAN DEFAULT FALSE,
    notes JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (trade_date, sector_code)
);

COMMENT ON TABLE signals_sector_daily IS 'M-pool sector daily signals for the 11 SPDR sector ETFs.';
COMMENT ON COLUMN signals_sector_daily.trade_date IS 'US Eastern market close date for this sector signal row.';
COMMENT ON COLUMN signals_sector_daily.sector_code IS 'Sector ETF code such as XLK, XLF, or XLE.';
COMMENT ON COLUMN signals_sector_daily.sector_name IS 'Human-readable sector name.';
COMMENT ON COLUMN signals_sector_daily.sector_chg_pct IS 'Sector daily percentage change.';
COMMENT ON COLUMN signals_sector_daily.relative_strength IS 'Sector relative strength versus SPX over the configured 20-day window.';
COMMENT ON COLUMN signals_sector_daily.breadth_above_50ma_pct IS 'Percent of sector members above 50-day moving average.';
COMMENT ON COLUMN signals_sector_daily.top_movers IS 'Top sector movers as JSON array, e.g. [{symbol, chg_pct}].';
COMMENT ON COLUMN signals_sector_daily.triggers_hit IS 'Sector-level trigger chain hit flags.';
COMMENT ON COLUMN signals_sector_daily.chain_details IS 'Detailed parameters and evidence for sector signal chains.';
COMMENT ON COLUMN signals_sector_daily.sector_grade IS 'Sector grade: S, A, B, C, or D.';
COMMENT ON COLUMN signals_sector_daily.grade_stable_days IS 'Consecutive days the current sector grade has persisted.';
COMMENT ON COLUMN signals_sector_daily.prev_grade IS 'Previous sector grade before the current trade date.';
COMMENT ON COLUMN signals_sector_daily.layer1_flag IS 'Whether this sector row should appear in the first-layer daily report.';
COMMENT ON COLUMN signals_sector_daily.layer2_flag IS 'Whether this sector row should appear in the second-layer daily report.';
COMMENT ON COLUMN signals_sector_daily.notes IS 'Free-form diagnostics or manual notes for sector signals.';
COMMENT ON COLUMN signals_sector_daily.created_at IS 'Row creation timestamp.';
COMMENT ON COLUMN signals_sector_daily.updated_at IS 'Application-maintained row update timestamp.';

CREATE INDEX IF NOT EXISTS idx_signals_sector_daily_sector_date ON signals_sector_daily (sector_code, trade_date DESC);
CREATE INDEX IF NOT EXISTS idx_signals_sector_daily_sector_grade ON signals_sector_daily (sector_grade);

CREATE TABLE IF NOT EXISTS signals_theme_daily (
    trade_date DATE NOT NULL,
    theme_code VARCHAR(40) NOT NULL,
    theme_name VARCHAR(80),
    member_count INTEGER,
    theme_chg_pct NUMERIC(6,2),
    relative_strength NUMERIC(6,2),
    breadth_above_50ma_pct NUMERIC(5,2),
    top_movers JSONB,
    triggers_hit JSONB,
    chain_details JSONB,
    theme_grade VARCHAR(10),
    grade_stable_days INTEGER,
    prev_grade VARCHAR(10),
    layer1_flag BOOLEAN DEFAULT FALSE,
    layer2_flag BOOLEAN DEFAULT FALSE,
    notes JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (trade_date, theme_code)
);

COMMENT ON TABLE signals_theme_daily IS 'M-pool theme daily signals for dynamic themes from themes.yaml.';
COMMENT ON COLUMN signals_theme_daily.trade_date IS 'US Eastern market close date for this theme signal row.';
COMMENT ON COLUMN signals_theme_daily.theme_code IS 'Stable theme identifier such as ai_infra or cyber_security.';
COMMENT ON COLUMN signals_theme_daily.theme_name IS 'Human-readable theme name.';
COMMENT ON COLUMN signals_theme_daily.member_count IS 'Effective member count for the theme on this trade date.';
COMMENT ON COLUMN signals_theme_daily.theme_chg_pct IS 'Theme daily percentage change, equal-weighted or market-cap-weighted by implementation.';
COMMENT ON COLUMN signals_theme_daily.relative_strength IS 'Theme relative strength versus benchmark over configured window.';
COMMENT ON COLUMN signals_theme_daily.breadth_above_50ma_pct IS 'Percent of theme members above 50-day moving average.';
COMMENT ON COLUMN signals_theme_daily.top_movers IS 'Top theme movers as JSON array, e.g. [{symbol, chg_pct}].';
COMMENT ON COLUMN signals_theme_daily.triggers_hit IS 'Theme-level trigger chain hit flags.';
COMMENT ON COLUMN signals_theme_daily.chain_details IS 'Detailed parameters and evidence for theme signal chains.';
COMMENT ON COLUMN signals_theme_daily.theme_grade IS 'Theme grade: S, A, B, C, or D.';
COMMENT ON COLUMN signals_theme_daily.grade_stable_days IS 'Consecutive days the current theme grade has persisted.';
COMMENT ON COLUMN signals_theme_daily.prev_grade IS 'Previous theme grade before the current trade date.';
COMMENT ON COLUMN signals_theme_daily.layer1_flag IS 'Whether this theme row should appear in the first-layer daily report.';
COMMENT ON COLUMN signals_theme_daily.layer2_flag IS 'Whether this theme row should appear in the second-layer daily report.';
COMMENT ON COLUMN signals_theme_daily.notes IS 'Free-form diagnostics or manual notes for theme signals.';
COMMENT ON COLUMN signals_theme_daily.created_at IS 'Row creation timestamp.';
COMMENT ON COLUMN signals_theme_daily.updated_at IS 'Application-maintained row update timestamp.';

CREATE INDEX IF NOT EXISTS idx_signals_theme_daily_theme_date ON signals_theme_daily (theme_code, trade_date DESC);
CREATE INDEX IF NOT EXISTS idx_signals_theme_daily_theme_grade ON signals_theme_daily (theme_grade);

CREATE TABLE IF NOT EXISTS signals_stock_daily (
    trade_date DATE NOT NULL,
    symbol VARCHAR(10) NOT NULL,
    close NUMERIC(10,2),
    chg_pct NUMERIC(6,2),
    volume_ratio NUMERIC(6,2),
    dist_50ma_pct NUMERIC(6,2),
    dist_200ma_pct NUMERIC(6,2),
    dist_52w_high_pct NUMERIC(6,2),
    dist_52w_low_pct NUMERIC(6,2),
    rsi_14 NUMERIC(5,2),
    atr_pct NUMERIC(5,2),
    triggers_hit JSONB,
    chain_details JSONB,
    stock_grade VARCHAR(10),
    grade_stable_days INTEGER,
    prev_grade VARCHAR(10),
    regime_at_signal VARCHAR(20),
    sector_code VARCHAR(20),
    theme_codes JSONB,
    layer1_flag BOOLEAN DEFAULT FALSE,
    layer2_flag BOOLEAN DEFAULT FALSE,
    notes JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (trade_date, symbol)
);

COMMENT ON TABLE signals_stock_daily IS 'M-pool stock daily signals for all active symbol_universe members.';
COMMENT ON COLUMN signals_stock_daily.trade_date IS 'US Eastern market close date for this stock signal row.';
COMMENT ON COLUMN signals_stock_daily.symbol IS 'Stock ticker symbol.';
COMMENT ON COLUMN signals_stock_daily.close IS 'Stock close price.';
COMMENT ON COLUMN signals_stock_daily.chg_pct IS 'Stock daily percentage change.';
COMMENT ON COLUMN signals_stock_daily.volume_ratio IS 'Daily volume divided by 20-day average volume.';
COMMENT ON COLUMN signals_stock_daily.dist_50ma_pct IS 'Distance from 50-day moving average, percent.';
COMMENT ON COLUMN signals_stock_daily.dist_200ma_pct IS 'Distance from 200-day moving average, percent.';
COMMENT ON COLUMN signals_stock_daily.dist_52w_high_pct IS 'Distance from 52-week high, percent.';
COMMENT ON COLUMN signals_stock_daily.dist_52w_low_pct IS 'Distance from 52-week low, percent.';
COMMENT ON COLUMN signals_stock_daily.rsi_14 IS '14-day RSI.';
COMMENT ON COLUMN signals_stock_daily.atr_pct IS 'ATR as percent of close.';
COMMENT ON COLUMN signals_stock_daily.triggers_hit IS 'Stock-level seven-chain trigger hit flags.';
COMMENT ON COLUMN signals_stock_daily.chain_details IS 'Detailed parameters and evidence for stock signal chains.';
COMMENT ON COLUMN signals_stock_daily.stock_grade IS 'Stock grade: S, A, B, C, or D.';
COMMENT ON COLUMN signals_stock_daily.grade_stable_days IS 'Consecutive days the current stock grade has persisted.';
COMMENT ON COLUMN signals_stock_daily.prev_grade IS 'Previous stock grade before the current trade date.';
COMMENT ON COLUMN signals_stock_daily.regime_at_signal IS 'Market regime at the time this stock signal was generated.';
COMMENT ON COLUMN signals_stock_daily.sector_code IS 'Sector code associated with the stock.';
COMMENT ON COLUMN signals_stock_daily.theme_codes IS 'Theme identifiers associated with the stock, e.g. ["ai_infra", "semis"].';
COMMENT ON COLUMN signals_stock_daily.layer1_flag IS 'Whether this stock row should appear in the first-layer daily report.';
COMMENT ON COLUMN signals_stock_daily.layer2_flag IS 'Whether this stock row should appear in the second-layer daily report.';
COMMENT ON COLUMN signals_stock_daily.notes IS 'Free-form diagnostics or manual notes for stock signals.';
COMMENT ON COLUMN signals_stock_daily.created_at IS 'Row creation timestamp.';
COMMENT ON COLUMN signals_stock_daily.updated_at IS 'Application-maintained row update timestamp.';

CREATE INDEX IF NOT EXISTS idx_signals_stock_daily_symbol_date ON signals_stock_daily (symbol, trade_date DESC);
CREATE INDEX IF NOT EXISTS idx_signals_stock_daily_trade_date_grade ON signals_stock_daily (trade_date, stock_grade);
CREATE INDEX IF NOT EXISTS idx_signals_stock_daily_sector_date ON signals_stock_daily (sector_code, trade_date DESC);
CREATE INDEX IF NOT EXISTS idx_signals_stock_daily_layer2_trade_date ON signals_stock_daily (trade_date) WHERE layer2_flag = TRUE;
