-- migrate:up
BEGIN;

ALTER TABLE macro_daily
    ADD COLUMN IF NOT EXISTS us2y NUMERIC(18,4);

COMMIT;

-- migrate:down
BEGIN;

ALTER TABLE macro_daily
    DROP COLUMN IF EXISTS us2y;

COMMIT;
