-- Rebuild silver.employee from bronze.employee_raw (full refresh).
-- Runs in one transaction with the caller: TRUNCATE is transactional in
-- Postgres, so if the INSERT fails the previous silver data is restored.

TRUNCATE silver.employee;

INSERT INTO silver.employee (
    client_employee_id, first_name, middle_name, last_name, preferred_name,
    job_code, job_title, job_start_date, organization_id, organization_name,
    department_id, department_name, dob, hire_date, recent_hire_date,
    anniversary_date, term_date, years_of_experience, work_email, address,
    city, state, zip, country, manager_employee_id, manager_employee_name,
    fte_status, is_per_deim, cell_phone, work_phone, scheduled_weekly_hour,
    active_status, termination_reason, clinical_level,
    is_per_diem, source_file, source_row_num
)
-- DISTINCT ON keeps one row per employee: the copy from the latest extract.
-- With a single employee file it removes nothing, but without it a second
-- extract in bronze would break the primary key.
SELECT DISTINCT ON (client_employee_id) *
FROM (
    SELECT
        silver.clean_text(client_employee_id)                    AS client_employee_id,
        silver.clean_text(first_name)                            AS first_name,
        silver.clean_text(middle_name)                           AS middle_name,
        silver.clean_text(last_name)                             AS last_name,
        silver.clean_text(preferred_name)                        AS preferred_name,
        silver.clean_text(job_code)                              AS job_code,
        silver.clean_text(job_title)                             AS job_title,
        silver.clean_text(job_start_date)::DATE                  AS job_start_date,
        silver.clean_text(organization_id)                       AS organization_id,
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
        silver.clean_text(dob)::DATE                             AS dob,
        silver.clean_text(hire_date)::DATE                       AS hire_date,
        silver.clean_text(recent_hire_date)::DATE                AS recent_hire_date,
        silver.clean_text(anniversary_date)::DATE                AS anniversary_date,
        silver.clean_text(term_date)::DATE                       AS term_date,
        silver.clean_text(years_of_experience)                   AS years_of_experience,
        silver.clean_text(work_email)                            AS work_email,
        silver.clean_text(address)                               AS address,
        silver.clean_text(city)                                  AS city,
        silver.clean_text(state)                                 AS state,
        silver.clean_text(zip)                                   AS zip,
        silver.clean_text(country)                               AS country,
        silver.clean_text(manager_employee_id)                   AS manager_employee_id,
        silver.clean_text(manager_employee_name)                 AS manager_employee_name,
        silver.clean_text(fte_status)                            AS fte_status,
        silver.clean_text(is_per_deim)                           AS is_per_deim,
        silver.clean_text(cell_phone)                            AS cell_phone,
        silver.clean_text(work_phone)                            AS work_phone,
        silver.clean_text(scheduled_weekly_hour)::NUMERIC(5,2)   AS scheduled_weekly_hour,
        silver.clean_text(active_status)::BOOLEAN                AS active_status,  -- '1'/'0' -> true/false
        silver.clean_text(termination_reason)                    AS termination_reason,
        silver.clean_text(clinical_level)                        AS clinical_level,
        -- Per diem: the source flag wins when it holds a recognized value;
        -- otherwise fall back to the job title ending in '- PD' (an assumption
        -- accepted by the data provider, see docs/assumptions.md). The last
        -- false covers a missing title, since the column is NOT NULL.
        -- Unrecognized source values silently fall back here; Step 2's
        -- cleaning log counts them, so the fallback never hides bad source data.
        COALESCE(
            CASE
                WHEN lower(silver.clean_text(is_per_deim)) IN ('1', 'true', 'y')  THEN true
                WHEN lower(silver.clean_text(is_per_deim)) IN ('0', 'false', 'n') THEN false
            END,
            silver.clean_text(job_title) LIKE '%- PD',
            false
        )                                                        AS is_per_diem,
        source_file,
        source_row_num
    FROM bronze.employee_raw
) AS cleaned
-- "Latest extract wins" relies on the file names sorting by extraction time
-- (employee_YYYYMMDDHHMM.csv), so source_file DESC = newest first.
ORDER BY client_employee_id, source_file DESC;
