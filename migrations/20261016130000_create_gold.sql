-- Gold layer: star schema built from silver by pipeline/build_gold.py.

CREATE SCHEMA IF NOT EXISTS gold;

-- One row per calendar day (course Week4 pattern).
CREATE TABLE IF NOT EXISTS gold.dim_date (
    date_key        INTEGER      PRIMARY KEY,      -- e.g. 20250918
    full_date       DATE         NOT NULL UNIQUE,
    year            SMALLINT     NOT NULL,
    quarter         SMALLINT     NOT NULL CHECK (quarter BETWEEN 1 AND 4),
    month           SMALLINT     NOT NULL CHECK (month BETWEEN 1 AND 12),
    month_name      VARCHAR(10)  NOT NULL,          -- 'January' … 'December'
    week_of_year    SMALLINT     NOT NULL,          -- ISO week 1-53
    day_of_week     SMALLINT     NOT NULL CHECK (day_of_week BETWEEN 0 AND 6), -- 0=Sun
    day_name        VARCHAR(10)  NOT NULL,          -- 'Sunday' … 'Saturday'
    is_weekend      BOOLEAN      NOT NULL
);

-- One row per department ID seen in silver.
CREATE TABLE IF NOT EXISTS gold.dim_department (
    department_key    INTEGER       GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    department_id     TEXT          NOT NULL UNIQUE,
    department_name   TEXT,
    department_label  TEXT          NOT NULL,                -- e.g. 'CT Scan (201-10078)'
    loaded_at         TIMESTAMPTZ   NOT NULL DEFAULT now()
);

-- One row per employee, SCD Type 1; inferred employees have only the ID.
-- Personal and de-identified fields are dropped at bronze -> silver (confirmed by the data provider).
CREATE TABLE IF NOT EXISTS gold.dim_employee (
    employee_key           INTEGER       GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    client_employee_id     TEXT          NOT NULL UNIQUE,
    first_name             TEXT,
    job_code               TEXT,
    job_title              TEXT,
    job_start_date         DATE,
    organization_name      TEXT,
    department_id          TEXT,
    department_name        TEXT,
    fte_status             TEXT,
    scheduled_weekly_hour  NUMERIC(5,2),
    manager_employee_id    TEXT,
    hire_date              DATE,
    recent_hire_date       DATE,
    term_date              DATE,
    active_status          BOOLEAN,
    termination_reason     TEXT,
    is_per_diem            BOOLEAN,                         -- NULL for inferred employees
    is_inferred            BOOLEAN       NOT NULL,
    source_file            TEXT,                            -- NULL for inferred employees
    source_row_num         INTEGER,
    loaded_at              TIMESTAMPTZ   NOT NULL DEFAULT now(),
    CHECK (is_inferred = (source_file IS NULL))             -- real employees always have lineage
);

-- One row per punch, same grain as silver.timesheet.
-- The natural key (employee, punch-in) identifies each punch, so there is no surrogate key.
CREATE TABLE IF NOT EXISTS gold.fact_timesheet (
    employee_key              INTEGER       NOT NULL REFERENCES gold.dim_employee (employee_key),
    date_key                  INTEGER       NOT NULL REFERENCES gold.dim_date (date_key),
    department_key            INTEGER       REFERENCES gold.dim_department (department_key),  -- NULL when no department
    home_department_key       INTEGER       REFERENCES gold.dim_department (department_key),  -- NULL when no home department
    client_employee_id        TEXT          NOT NULL,
    pay_code                  TEXT,
    punch_in_comment          TEXT,
    punch_out_comment         TEXT,
    hours_worked              NUMERIC(5,2),
    punch_apply_date          DATE          NOT NULL,
    punch_in_datetime         TIMESTAMP     NOT NULL,
    punch_out_datetime        TIMESTAMP,
    scheduled_start_datetime  TIMESTAMP,
    scheduled_end_datetime    TIMESTAMP,
    has_schedule              BOOLEAN       NOT NULL,  -- from silver
    is_incomplete             BOOLEAN       NOT NULL,  -- from silver
    source_file               TEXT          NOT NULL,
    source_row_num            INTEGER       NOT NULL,
    loaded_at                 TIMESTAMPTZ   NOT NULL DEFAULT now(),
    PRIMARY KEY (employee_key, punch_in_datetime)
);
