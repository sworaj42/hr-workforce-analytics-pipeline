-- Rebuild silver.employee and silver.employee_rejects from bronze (full refresh).
-- Runs in one transaction with the caller, so a failure keeps the previous data.

TRUNCATE silver.employee, silver.employee_rejects;

-- Bronze rows as they are, plus the first rule each row fails (NULL = valid).
-- pg_input_is_valid(NULL, ...) is NULL, so a missing optional value passes.
-- Casts are checked first, so the comparison rule only sees valid values.
CREATE TEMP TABLE checked ON COMMIT DROP AS
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
FROM checked
WHERE reject_reason IS NOT NULL;

INSERT INTO silver.employee (
    client_employee_id, first_name, last_name, job_code, job_title,
    job_start_date, organization_name, department_id, department_name,
    manager_employee_id, fte_status, scheduled_weekly_hour, hire_date,
    recent_hire_date, anniversary_date, term_date, active_status,
    termination_reason, is_per_diem, source_file, source_row_num
)
-- DISTINCT ON keeps one row per employee: the copy from the latest extract.
-- With a single employee file it removes nothing, but without it a second
-- extract in bronze would break the primary key.
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
        -- Strip the exact '<department_id>-' prefix ('72800-CT Scan' -> 'CT Scan').
        -- Cut by the ID's length rather than at the first hyphen, because some
        -- IDs contain one ('8000-13204-RCM Registration' -> 'RCM Registration').
        -- left() instead of LIKE so '%' or '_' in an ID can't act as wildcards;
        -- a name without the prefix is kept as it is.
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
        -- Per diem: job title ends in '- PD' (assumption, see docs/assumptions.md).
        -- false when the title is missing, since the column is NOT NULL.
        COALESCE(silver.clean_text(job_title) LIKE '%- PD', false) AS is_per_diem,
        source_file,
        source_row_num
    FROM checked
    WHERE reject_reason IS NULL
) AS cleaned
-- "Latest extract wins" relies on the file names sorting by extraction time
-- (employee_YYYYMMDDHHMM.csv), so source_file DESC = newest first.
ORDER BY client_employee_id, source_file DESC;
