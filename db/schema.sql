CREATE TABLE IF NOT EXISTS quotes_daily (
    symbol TEXT NOT NULL,
    trade_date DATE NOT NULL,
    open NUMERIC(18,4),
    high NUMERIC(18,4),
    low NUMERIC(18,4),
    close NUMERIC(18,4),
    adj_close NUMERIC(18,4),
    volume BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (symbol, trade_date)
);

CREATE TABLE IF NOT EXISTS macro_daily (
    trade_date DATE PRIMARY KEY,
    vix NUMERIC(18,4),
    spy NUMERIC(18,4),
    qqq NUMERIC(18,4),
    tlt NUMERIC(18,4),
    gld NUMERIC(18,4),
    uup NUMERIC(18,4),
    hyg NUMERIC(18,4),
    lqd NUMERIC(18,4),
    dxy NUMERIC(18,4),
    wti NUMERIC(18,4),
    btc NUMERIC(18,4),
    ief NUMERIC(18,4),
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
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
