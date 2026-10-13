-- Silver layer: cleaned, typed and deduplicated rows built from bronze.
-- One row per punch; the primary key makes the database enforce that the
-- duplicates from overlapping extracts never reach this layer.
-- source_file + source_row_num point at the bronze row each record came from.

CREATE SCHEMA IF NOT EXISTS silver;

-- The one rule for raw text values: trim spaces, then treat '' and the
-- literal '[NULL]' used by the source system as missing.
-- IMMUTABLE (same input -> same output) lets Postgres inline it like a plain expression.
CREATE OR REPLACE FUNCTION silver.clean_text(value TEXT) RETURNS TEXT
LANGUAGE sql IMMUTABLE
AS $$ SELECT NULLIF(NULLIF(TRIM(value), ''), '[NULL]') $$;

CREATE TABLE IF NOT EXISTS silver.timesheet (
    client_employee_id        TEXT          NOT NULL,  -- TEXT: some IDs are zero-padded
    department_id             TEXT,
    department_name           TEXT,
    home_department_id        TEXT,
    home_department_name      TEXT,
    pay_code                  TEXT,
    punch_in_comment          TEXT,
    punch_out_comment         TEXT,
    hours_worked              NUMERIC(5,2),            -- exact decimal; source always has 2 places
    punch_apply_date          DATE,
    -- TIMESTAMP without time zone: the source carries no zone, so these are
    -- kept as local wall-clock times (assumed US Eastern, Massachusetts).
    punch_in_datetime         TIMESTAMP     NOT NULL,
    punch_out_datetime        TIMESTAMP,
    scheduled_start_datetime  TIMESTAMP,
    scheduled_end_datetime    TIMESTAMP,

    source_file               TEXT          NOT NULL,
    source_row_num            INTEGER       NOT NULL,
    loaded_at                 TIMESTAMPTZ   NOT NULL DEFAULT now(),

    PRIMARY KEY (client_employee_id, punch_in_datetime)
);
