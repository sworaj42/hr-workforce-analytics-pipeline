-- Upsert silver.employee from bronze and refill its rejects (one transaction).
-- A full reload truncates silver.employee first (build_silver.py).

TRUNCATE silver.employee_rejects;

-- Raw bronze rows plus the first rule each fails (NULL = valid; missing optional values pass).
CREATE TEMP TABLE checked_employee ON COMMIT DROP AS
SELECT
    client_employee_id, first_name, last_name, job_code, job_title,
    job_start_date, organization_name, department_id, department_name,
    manager_employee_id, fte_status, scheduled_weekly_hour, hire_date,
    recent_hire_date, anniversary_date, term_date, active_status,
    termination_reason, source_file, source_row_num,
    CASE
        WHEN silver.clean_text(client_employee_id) IS NULL
            THEN 'missing client_employee_id'
        WHEN NOT pg_input_is_valid(silver.clean_text(job_start_date), 'date')
            THEN 'invalid job_start_date'
        WHEN NOT pg_input_is_valid(silver.clean_text(hire_date), 'date')
            THEN 'invalid hire_date'
        WHEN NOT pg_input_is_valid(silver.clean_text(recent_hire_date), 'date')
            THEN 'invalid recent_hire_date'
        WHEN NOT pg_input_is_valid(silver.clean_text(anniversary_date), 'date')
            THEN 'invalid anniversary_date'
        WHEN NOT pg_input_is_valid(silver.clean_text(term_date), 'date')
            THEN 'invalid term_date'
        WHEN NOT pg_input_is_valid(silver.clean_text(active_status), 'boolean')
            THEN 'invalid active_status'
        WHEN NOT pg_input_is_valid(silver.clean_text(scheduled_weekly_hour), 'numeric(5,2)')
            THEN 'invalid scheduled_weekly_hour'
        WHEN silver.clean_text(term_date)::DATE < silver.clean_text(hire_date)::DATE
            THEN 'term_date before hire_date'
    END AS reject_reason
FROM bronze.employee_raw;

INSERT INTO silver.employee_rejects (
    client_employee_id, first_name, last_name, job_code, job_title,
    job_start_date, organization_name, department_id, department_name,
    manager_employee_id, fte_status, scheduled_weekly_hour, hire_date,
    recent_hire_date, anniversary_date, term_date, active_status,
    termination_reason, reject_reason, source_file, source_row_num
)
SELECT
    client_employee_id, first_name, last_name, job_code, job_title,
    job_start_date, organization_name, department_id, department_name,
    manager_employee_id, fte_status, scheduled_weekly_hour, hire_date,
    recent_hire_date, anniversary_date, term_date, active_status,
    termination_reason, reject_reason, source_file, source_row_num
FROM checked_employee
WHERE reject_reason IS NOT NULL;

INSERT INTO silver.employee (
    client_employee_id, first_name, last_name, job_code, job_title,
    job_start_date, organization_name, department_id, department_name,
    manager_employee_id, fte_status, scheduled_weekly_hour, hire_date,
    recent_hire_date, anniversary_date, term_date, active_status,
    termination_reason, is_per_diem, source_file, source_row_num
)
-- One row per employee: the copy from the latest extract.
SELECT DISTINCT ON (client_employee_id) *
FROM (
    SELECT
        silver.clean_text(client_employee_id)                    AS client_employee_id,
        silver.clean_text(first_name)                            AS first_name,
        silver.clean_text(last_name)                             AS last_name,
        silver.clean_text(job_code)                              AS job_code,
        silver.clean_text(job_title)                             AS job_title,
        silver.clean_text(job_start_date)::DATE                  AS job_start_date,
        silver.clean_text(organization_name)                     AS organization_name,
        silver.clean_text(department_id)                         AS department_id,
        -- Strip the exact '<department_id>-' prefix; some IDs contain a hyphen.
        CASE
            WHEN left(silver.clean_text(department_name), length(silver.clean_text(department_id)) + 1)
                 = silver.clean_text(department_id) || '-'
            THEN substr(silver.clean_text(department_name), length(silver.clean_text(department_id)) + 2)
            ELSE silver.clean_text(department_name)
        END                                                      AS department_name,
        silver.clean_text(manager_employee_id)                   AS manager_employee_id,
        silver.clean_text(fte_status)                            AS fte_status,
        silver.clean_text(scheduled_weekly_hour)::NUMERIC(5,2)   AS scheduled_weekly_hour,
        silver.clean_text(hire_date)::DATE                       AS hire_date,
        silver.clean_text(recent_hire_date)::DATE                AS recent_hire_date,
        silver.clean_text(anniversary_date)::DATE                AS anniversary_date,
        silver.clean_text(term_date)::DATE                       AS term_date,
        silver.clean_text(active_status)::BOOLEAN                AS active_status,  -- '1'/'0' -> true/false
        silver.clean_text(termination_reason)                    AS termination_reason,
        -- Assumption: title ending in '- PD' means per diem; false if no title.
        COALESCE(silver.clean_text(job_title) LIKE '%- PD', false) AS is_per_diem,
        source_file,
        source_row_num
    FROM checked_employee
    WHERE reject_reason IS NULL
) AS cleaned
-- Newest file first: names sort by extraction time (employee_YYYYMMDDHHMM.csv).
ORDER BY client_employee_id, source_file DESC
-- Only a new file overwrites a row, so API edits survive reruns of the same file.
-- is_deleted isn't updated (deletes stick); rows missing from the file are kept.
ON CONFLICT (client_employee_id) DO UPDATE SET
    first_name            = EXCLUDED.first_name,
    last_name             = EXCLUDED.last_name,
    job_code              = EXCLUDED.job_code,
    job_title             = EXCLUDED.job_title,
    job_start_date        = EXCLUDED.job_start_date,
    organization_name     = EXCLUDED.organization_name,
    department_id         = EXCLUDED.department_id,
    department_name       = EXCLUDED.department_name,
    manager_employee_id   = EXCLUDED.manager_employee_id,
    fte_status            = EXCLUDED.fte_status,
    scheduled_weekly_hour = EXCLUDED.scheduled_weekly_hour,
    hire_date             = EXCLUDED.hire_date,
    recent_hire_date      = EXCLUDED.recent_hire_date,
    anniversary_date      = EXCLUDED.anniversary_date,
    term_date             = EXCLUDED.term_date,
    active_status         = EXCLUDED.active_status,
    termination_reason    = EXCLUDED.termination_reason,
    is_per_diem           = EXCLUDED.is_per_diem,
    source_file           = EXCLUDED.source_file,
    source_row_num        = EXCLUDED.source_row_num,
    loaded_at             = now()
WHERE silver.employee.source_file IS DISTINCT FROM EXCLUDED.source_file;
