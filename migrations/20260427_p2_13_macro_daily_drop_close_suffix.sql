-- migrate:up
BEGIN;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'macro_daily' AND column_name = 'spy_close'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'macro_daily' AND column_name = 'spy'
    ) THEN
        ALTER TABLE macro_daily RENAME COLUMN spy_close TO spy;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'macro_daily' AND column_name = 'qqq_close'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'macro_daily' AND column_name = 'qqq'
    ) THEN
        ALTER TABLE macro_daily RENAME COLUMN qqq_close TO qqq;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'macro_daily' AND column_name = 'tlt_close'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'macro_daily' AND column_name = 'tlt'
    ) THEN
        ALTER TABLE macro_daily RENAME COLUMN tlt_close TO tlt;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'macro_daily' AND column_name = 'gld_close'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'macro_daily' AND column_name = 'gld'
    ) THEN
        ALTER TABLE macro_daily RENAME COLUMN gld_close TO gld;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'macro_daily' AND column_name = 'uup_close'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'macro_daily' AND column_name = 'uup'
    ) THEN
        ALTER TABLE macro_daily RENAME COLUMN uup_close TO uup;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'macro_daily' AND column_name = 'hyg_close'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'macro_daily' AND column_name = 'hyg'
    ) THEN
        ALTER TABLE macro_daily RENAME COLUMN hyg_close TO hyg;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'macro_daily' AND column_name = 'lqd_close'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'macro_daily' AND column_name = 'lqd'
    ) THEN
        ALTER TABLE macro_daily RENAME COLUMN lqd_close TO lqd;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'macro_daily' AND column_name = 'btc_close'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'macro_daily' AND column_name = 'btc'
    ) THEN
        ALTER TABLE macro_daily RENAME COLUMN btc_close TO btc;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'macro_daily' AND column_name = 'ief_close'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'macro_daily' AND column_name = 'ief'
    ) THEN
        ALTER TABLE macro_daily RENAME COLUMN ief_close TO ief;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'macro_daily' AND column_name = 'us10y'
    ) THEN
        ALTER TABLE macro_daily ADD COLUMN us10y NUMERIC(18,4);
    END IF;
END $$;

COMMIT;

-- migrate:down
BEGIN;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'macro_daily' AND column_name = 'spy'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'macro_daily' AND column_name = 'spy_close'
    ) THEN
        ALTER TABLE macro_daily RENAME COLUMN spy TO spy_close;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'macro_daily' AND column_name = 'qqq'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'macro_daily' AND column_name = 'qqq_close'
    ) THEN
        ALTER TABLE macro_daily RENAME COLUMN qqq TO qqq_close;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'macro_daily' AND column_name = 'tlt'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'macro_daily' AND column_name = 'tlt_close'
    ) THEN
        ALTER TABLE macro_daily RENAME COLUMN tlt TO tlt_close;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'macro_daily' AND column_name = 'gld'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'macro_daily' AND column_name = 'gld_close'
    ) THEN
        ALTER TABLE macro_daily RENAME COLUMN gld TO gld_close;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'macro_daily' AND column_name = 'uup'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'macro_daily' AND column_name = 'uup_close'
    ) THEN
        ALTER TABLE macro_daily RENAME COLUMN uup TO uup_close;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'macro_daily' AND column_name = 'hyg'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'macro_daily' AND column_name = 'hyg_close'
    ) THEN
        ALTER TABLE macro_daily RENAME COLUMN hyg TO hyg_close;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'macro_daily' AND column_name = 'lqd'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'macro_daily' AND column_name = 'lqd_close'
    ) THEN
        ALTER TABLE macro_daily RENAME COLUMN lqd TO lqd_close;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'macro_daily' AND column_name = 'btc'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'macro_daily' AND column_name = 'btc_close'
    ) THEN
        ALTER TABLE macro_daily RENAME COLUMN btc TO btc_close;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'macro_daily' AND column_name = 'ief'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'macro_daily' AND column_name = 'ief_close'
    ) THEN
        ALTER TABLE macro_daily RENAME COLUMN ief TO ief_close;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'macro_daily' AND column_name = 'us10y'
    ) THEN
        ALTER TABLE macro_daily DROP COLUMN us10y;
    END IF;
END $$;

COMMIT;
