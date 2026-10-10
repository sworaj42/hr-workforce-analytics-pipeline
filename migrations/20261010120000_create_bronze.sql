-- Bronze layer: raw rows exactly as they arrive from the source files.
-- Every source column is TEXT so that no value can fail on load; typing and
-- validation happen in silver, where bad rows are kept in a rejects table.
-- source_file + source_row_num trace each row back to its line in the file.

CREATE SCHEMA IF NOT EXISTS bronze;

CREATE TABLE IF NOT EXISTS bronze.employee_raw (
    client_employee_id     TEXT,
    first_name             TEXT,
    middle_name            TEXT,
    last_name              TEXT,
    preferred_name         TEXT,
    job_code               TEXT,
    job_title              TEXT,
    job_start_date         TEXT,
    organization_id        TEXT,
    organization_name      TEXT,
    department_id          TEXT,
    department_name        TEXT,
    dob                    TEXT,
    hire_date              TEXT,
    recent_hire_date       TEXT,
    anniversary_date       TEXT,
    term_date              TEXT,
    years_of_experience    TEXT,
    work_email             TEXT,
    address                TEXT,
    city                   TEXT,
    state                  TEXT,
    zip                    TEXT,
    country                TEXT,
    manager_employee_id    TEXT,
    manager_employee_name  TEXT,
    fte_status             TEXT,
    is_per_deim            TEXT,   -- spelling kept as in the source
    cell_phone             TEXT,
    work_phone             TEXT,
    scheduled_weekly_hour  TEXT,
    active_status          TEXT,
    termination_reason     TEXT,
    clinical_level         TEXT,

    source_file            TEXT        NOT NULL,
    source_row_num         INTEGER     NOT NULL,
    loaded_at              TIMESTAMPTZ NOT NULL DEFAULT now(),

    PRIMARY KEY (source_file, source_row_num)
);

CREATE TABLE IF NOT EXISTS bronze.timesheet_raw (
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

    source_file               TEXT        NOT NULL,
    source_row_num            INTEGER     NOT NULL,
    loaded_at                 TIMESTAMPTZ NOT NULL DEFAULT now(),

    PRIMARY KEY (source_file, source_row_num)
);
