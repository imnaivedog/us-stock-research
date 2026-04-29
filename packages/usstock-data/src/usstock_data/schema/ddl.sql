CREATE TABLE IF NOT EXISTS quotes_daily (
    symbol TEXT NOT NULL,
    trade_date DATE NOT NULL,
    open NUMERIC(18,4),
    high NUMERIC(18,4),
    low NUMERIC(18,4),
    close NUMERIC(18,4),
    adj_close NUMERIC(18,4),
    volume BIGINT,
    asset_class TEXT NOT NULL DEFAULT 'equity',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (symbol, trade_date)
);

CREATE INDEX IF NOT EXISTS idx_quotes_asset_class ON quotes_daily(asset_class);

CREATE TABLE IF NOT EXISTS macro_daily (
    trade_date DATE PRIMARY KEY,
    vix NUMERIC(18,4),
    spy NUMERIC(18,4),
    qqq NUMERIC(18,4),
    tlt NUMERIC(18,4),
    gld NUMERIC(18,4),
    silver NUMERIC(18,4),
    gold_silver_ratio NUMERIC(18,4),
    uup NUMERIC(18,4),
    hyg NUMERIC(18,4),
    lqd NUMERIC(18,4),
    hyg_lqd_spread NUMERIC(18,4),
    dxy NUMERIC(18,4),
    wti NUMERIC(18,4),
    btc NUMERIC(18,4),
    ief NUMERIC(18,4),
    us10y NUMERIC(18,4),
    us2y NUMERIC(18,4),
    dgs10 NUMERIC(18,4),
    dgs2 NUMERIC(18,4),
    spread_10y_2y NUMERIC(18,4),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sp500_members_daily (
    as_of_date DATE NOT NULL,
    symbol TEXT NOT NULL,
    index_name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (as_of_date, symbol, index_name)
);

CREATE TABLE IF NOT EXISTS etf_holdings_latest (
    etf_code TEXT NOT NULL,
    symbol TEXT NOT NULL,
    weight NUMERIC(18,4),
    as_of_date DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (etf_code, symbol)
);

CREATE TABLE IF NOT EXISTS symbol_universe (
    symbol TEXT PRIMARY KEY,
    pool TEXT NOT NULL DEFAULT 'm',
    source TEXT,
    source_secondary JSONB DEFAULT '[]'::jsonb,
    is_candidate BOOLEAN DEFAULT TRUE,
    is_active BOOLEAN,
    market_cap NUMERIC(18,4),
    adv_20d NUMERIC(18,4),
    ipo_date DATE,
    added_date DATE,
    last_seen_date DATE,
    removed_date DATE,
    as_of_date DATE,
    filter_reason TEXT,
    first_seen DATE,
    last_seen DATE,
    thesis_url TEXT,
    target_market_cap NUMERIC,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_su_active ON symbol_universe(is_active);
CREATE INDEX IF NOT EXISTS idx_su_last_seen ON symbol_universe(last_seen);
CREATE INDEX IF NOT EXISTS idx_symbol_universe_pool ON symbol_universe(pool);

CREATE TABLE IF NOT EXISTS symbol_universe_changes (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR NOT NULL REFERENCES symbol_universe(symbol),
    change_date DATE NOT NULL DEFAULT CURRENT_DATE,
    change_type VARCHAR NOT NULL CHECK (change_type IN ('added','removed','forced_in')),
    reason VARCHAR,
    market_cap NUMERIC,
    pool TEXT,
    thesis_url TEXT,
    target_market_cap NUMERIC,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_suc_symbol ON symbol_universe_changes(symbol);
CREATE INDEX IF NOT EXISTS idx_suc_date ON symbol_universe_changes(change_date);

CREATE TABLE IF NOT EXISTS watchlist (
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

CREATE INDEX IF NOT EXISTS idx_watchlist_status ON watchlist(status);
CREATE INDEX IF NOT EXISTS idx_watchlist_sector ON watchlist(sector);

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
    macro_state TEXT CHECK (macro_state IN ('risk_on', 'risk_off', 'neutral')),
    as_of_date DATE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (trade_date)
);

CREATE INDEX IF NOT EXISTS idx_sd_regime ON signals_daily(regime);
CREATE INDEX IF NOT EXISTS idx_sd_as_of ON signals_daily(as_of_date);
CREATE INDEX IF NOT EXISTS idx_sd_macro_state ON signals_daily(macro_state);

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

CREATE TABLE IF NOT EXISTS alert_log (
    id BIGSERIAL PRIMARY KEY,
    job_name TEXT NOT NULL,
    symbol TEXT,
    trade_date DATE,
    severity TEXT NOT NULL,
    message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_alert_log_date ON alert_log(trade_date);

CREATE TABLE IF NOT EXISTS corporate_actions (
    symbol TEXT NOT NULL,
    ex_date DATE NOT NULL,
    action_type TEXT NOT NULL,
    ratio FLOAT,
    cash_amount FLOAT,
    details JSONB,
    PRIMARY KEY (symbol, ex_date, action_type)
);

CREATE INDEX IF NOT EXISTS idx_corp_actions_date ON corporate_actions(ex_date);

CREATE TABLE IF NOT EXISTS events_calendar (
    symbol TEXT NOT NULL,
    event_date DATE NOT NULL,
    event_type TEXT NOT NULL,
    details JSONB,
    PRIMARY KEY (symbol, event_date, event_type)
);

CREATE TABLE IF NOT EXISTS fundamentals_quarterly (
    symbol TEXT NOT NULL,
    period_end DATE NOT NULL,
    fiscal_period TEXT NOT NULL,
    reported_at TIMESTAMPTZ,
    revenue FLOAT,
    eps_actual FLOAT,
    eps_estimate FLOAT,
    net_income FLOAT,
    operating_cash_flow FLOAT,
    free_cash_flow FLOAT,
    guidance JSONB,
    PRIMARY KEY (symbol, period_end)
);

CREATE INDEX IF NOT EXISTS idx_fund_q_reported ON fundamentals_quarterly(reported_at);

ALTER TABLE quotes_daily ADD COLUMN IF NOT EXISTS asset_class TEXT NOT NULL DEFAULT 'equity';
ALTER TABLE macro_daily ADD COLUMN IF NOT EXISTS silver NUMERIC(18,4);
ALTER TABLE macro_daily ADD COLUMN IF NOT EXISTS gold_silver_ratio NUMERIC(18,4);
ALTER TABLE macro_daily ADD COLUMN IF NOT EXISTS hyg_lqd_spread NUMERIC(18,4);
ALTER TABLE macro_daily ADD COLUMN IF NOT EXISTS ief NUMERIC(18,4);
ALTER TABLE macro_daily ADD COLUMN IF NOT EXISTS dxy NUMERIC(18,4);
ALTER TABLE macro_daily ADD COLUMN IF NOT EXISTS wti NUMERIC(18,4);
ALTER TABLE macro_daily ADD COLUMN IF NOT EXISTS btc NUMERIC(18,4);
ALTER TABLE macro_daily ADD COLUMN IF NOT EXISTS us10y NUMERIC(18,4);
ALTER TABLE macro_daily ADD COLUMN IF NOT EXISTS us2y NUMERIC(18,4);
ALTER TABLE macro_daily ADD COLUMN IF NOT EXISTS dgs10 NUMERIC(18,4);
ALTER TABLE macro_daily ADD COLUMN IF NOT EXISTS dgs2 NUMERIC(18,4);
ALTER TABLE macro_daily ADD COLUMN IF NOT EXISTS spread_10y_2y NUMERIC(18,4);
ALTER TABLE symbol_universe ADD COLUMN IF NOT EXISTS pool TEXT NOT NULL DEFAULT 'm';
ALTER TABLE symbol_universe ADD COLUMN IF NOT EXISTS thesis_url TEXT;
ALTER TABLE symbol_universe ADD COLUMN IF NOT EXISTS target_market_cap NUMERIC;
ALTER TABLE symbol_universe_changes ADD COLUMN IF NOT EXISTS pool TEXT;
ALTER TABLE symbol_universe_changes ADD COLUMN IF NOT EXISTS thesis_url TEXT;
ALTER TABLE symbol_universe_changes ADD COLUMN IF NOT EXISTS target_market_cap NUMERIC;
ALTER TABLE watchlist ADD COLUMN IF NOT EXISTS target_market_cap NUMERIC;
ALTER TABLE watchlist ADD COLUMN IF NOT EXISTS thesis_url VARCHAR;
ALTER TABLE watchlist ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();
