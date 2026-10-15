-- Silver layer: cleaned and typed employee rows built from bronze.
-- One row per employee. All 34 source columns are kept with their source
-- names, so silver mirrors the cleaned source; empty and constant columns
-- are left out later, in gold.
-- No CHECK constraints yet: validation rules and the rejects table come with
-- the cleaning step, and a CHECK here would fail the whole build on one row.
-- silver.clean_text() is defined in the silver timesheet migration.

CREATE SCHEMA IF NOT EXISTS silver;

CREATE TABLE IF NOT EXISTS silver.employee (
    client_employee_id     TEXT          NOT NULL,  -- TEXT: some IDs are zero-padded
    first_name             TEXT,
    middle_name            TEXT,
    last_name              TEXT,
    preferred_name         TEXT,
    job_code               TEXT,
    job_title              TEXT,
    job_start_date         DATE,
    organization_id        TEXT,
    organization_name      TEXT,
    department_id          TEXT,
    department_name        TEXT,                    -- cleaned: the 'department_id-' prefix is stripped in the transform
    dob                    DATE,
    hire_date              DATE,
    recent_hire_date       DATE,
    anniversary_date       DATE,
    term_date              DATE,
    years_of_experience    TEXT,                    -- TEXT: 100% empty, so its real format is unknown
    work_email             TEXT,
    address                TEXT,
    city                   TEXT,
    state                  TEXT,
    zip                    TEXT,                    -- TEXT: Massachusetts zip codes start with 0
    country                TEXT,
    manager_employee_id    TEXT,                    -- no FK: most managers are not in the employee file
    manager_employee_name  TEXT,
    fte_status             TEXT,
    is_per_deim            TEXT,                    -- spelling kept as in the source; TEXT because it is
                                                    -- 100% empty, so a BOOLEAN cast could fail on a future file
    cell_phone             TEXT,
    work_phone             TEXT,
    scheduled_weekly_hour  NUMERIC(5,2),            -- NUMERIC like hours_worked: weekly hours can be fractional (37.5)
    active_status          BOOLEAN,                 -- source has 1/0
    termination_reason     TEXT,
    clinical_level         TEXT,

    -- Derived in the transform: job_title ends in '- PD'. Evidence-based
    -- assumption, not a source field (is_per_deim is 100% empty): all 3
    -- Variable_time employees have '- PD' titles (plus 1 Part_time), and the
    -- only one with shifts (00080) books them all under the 'Per Diem' pay code,
    -- which no other employee uses. Pending confirmation from the instructor.
    is_per_diem            BOOLEAN       NOT NULL,

    source_file            TEXT          NOT NULL,
    source_row_num         INTEGER       NOT NULL,
    loaded_at              TIMESTAMPTZ   NOT NULL DEFAULT now(),

    PRIMARY KEY (client_employee_id)
);
