-- Silver layer: cleaned and typed tables built from bronze, plus reject tables.

CREATE SCHEMA IF NOT EXISTS silver;

-- Trim spaces; treat '' and the source's literal '[NULL]' as missing.
CREATE OR REPLACE FUNCTION silver.clean_text(value TEXT) RETURNS TEXT
LANGUAGE sql IMMUTABLE
AS $$ SELECT NULLIF(NULLIF(TRIM(value), ''), '[NULL]') $$;

-- One row per punch.
CREATE TABLE IF NOT EXISTS silver.timesheet (
    client_employee_id        TEXT          NOT NULL,  -- TEXT: zero-padded IDs
    department_id             TEXT,
    department_name           TEXT,
    home_department_id        TEXT,
    home_department_name      TEXT,
    pay_code                  TEXT,
    punch_in_comment          TEXT,
    punch_out_comment         TEXT,
    hours_worked              NUMERIC(5,2),            -- exact decimal
    punch_apply_date          DATE          NOT NULL,
    punch_in_datetime         TIMESTAMP     NOT NULL,  -- local wall-clock time, no zone in source
    punch_out_datetime        TIMESTAMP,
    scheduled_start_datetime  TIMESTAMP,
    scheduled_end_datetime    TIMESTAMP,
    source_file               TEXT          NOT NULL,
    source_row_num            INTEGER       NOT NULL,
    loaded_at                 TIMESTAMPTZ   NOT NULL DEFAULT now(),
    PRIMARY KEY (client_employee_id, punch_in_datetime)
);

-- Timesheet rows that failed validation, values exactly as in bronze.
CREATE TABLE IF NOT EXISTS silver.timesheet_rejects (
    client_employee_id        TEXT,
    department_id             TEXT,
    department_name           TEXT,
    home_department_id        TEXT,
    home_department_name      TEXT,
    pay_code                  TEXT,
    punch_in_comment          TEXT,
    punch_out_comment         TEXT,
    hours_worked              TEXT,
    punch_apply_date          TEXT,
    punch_in_datetime         TEXT,
    punch_out_datetime        TEXT,
    scheduled_start_datetime  TEXT,
    scheduled_end_datetime    TEXT,
    reject_reason             TEXT          NOT NULL,
    source_file               TEXT          NOT NULL,
    source_row_num            INTEGER       NOT NULL,
    rejected_at               TIMESTAMPTZ   NOT NULL DEFAULT now()
);

-- One row per employee. PII and masked fields dropped (confirmed by the data
-- provider); bronze keeps the full record.
CREATE TABLE IF NOT EXISTS silver.employee (
    client_employee_id        TEXT          NOT NULL,  -- TEXT: zero-padded IDs
    first_name                TEXT,                    -- API needs a name
    last_name                 TEXT,
    job_code                  TEXT,
    job_title                 TEXT,
    job_start_date            DATE,
    organization_name         TEXT,
    department_id             TEXT,
    department_name           TEXT,                    -- ID prefix stripped in the transform
    manager_employee_id       TEXT,
    fte_status                TEXT,
    scheduled_weekly_hour     NUMERIC(5,2),
    hire_date                 DATE,
    recent_hire_date          DATE,
    anniversary_date          DATE,
    term_date                 DATE,
    active_status             BOOLEAN,                 -- source has 1/0
    termination_reason        TEXT,
    is_per_diem               BOOLEAN       NOT NULL,  -- derived: job_title ends in '- PD' (assumption)
    source_file               TEXT          NOT NULL,
    source_row_num            INTEGER       NOT NULL,
    loaded_at                 TIMESTAMPTZ   NOT NULL DEFAULT now(),
    PRIMARY KEY (client_employee_id)
);

-- Employee rows that failed validation, values exactly as in bronze.
CREATE TABLE IF NOT EXISTS silver.employee_rejects (
    client_employee_id        TEXT,
    first_name                TEXT,
    last_name                 TEXT,
    job_code                  TEXT,
    job_title                 TEXT,
    job_start_date            TEXT,
    organization_name         TEXT,
    department_id             TEXT,
    department_name           TEXT,
    manager_employee_id       TEXT,
    fte_status                TEXT,
    scheduled_weekly_hour     TEXT,
    hire_date                 TEXT,
    recent_hire_date          TEXT,
    anniversary_date          TEXT,
    term_date                 TEXT,
    active_status             TEXT,
    termination_reason        TEXT,
    reject_reason             TEXT          NOT NULL,
    source_file               TEXT          NOT NULL,
    source_row_num            INTEGER       NOT NULL,
    rejected_at               TIMESTAMPTZ   NOT NULL DEFAULT now()
);

-- One row per silver table per successful build.
CREATE TABLE IF NOT EXISTS silver.cleaning_log (
    run_id                    TEXT          NOT NULL,  -- Airflow run_id, or manual__<time>
    table_name                TEXT          NOT NULL,  -- e.g. silver.timesheet
    load_mode                 TEXT          NOT NULL,  -- 'full' (incremental comes later)
    rows_read                 INTEGER       NOT NULL,
    rows_rejected             INTEGER       NOT NULL,
    rows_duplicate            INTEGER       NOT NULL,
    rows_loaded               INTEGER       NOT NULL,
    logged_at                 TIMESTAMPTZ   NOT NULL DEFAULT now()
);
