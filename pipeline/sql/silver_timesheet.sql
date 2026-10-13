-- Rebuild silver.timesheet from bronze.timesheet_raw (full refresh).
-- Runs in one transaction with the caller: TRUNCATE is transactional in
-- Postgres, so if the INSERT fails the previous silver data is restored.

TRUNCATE silver.timesheet;

INSERT INTO silver.timesheet (
    client_employee_id, department_id, department_name,
    home_department_id, home_department_name, pay_code,
    punch_in_comment, punch_out_comment, hours_worked, punch_apply_date,
    punch_in_datetime, punch_out_datetime,
    scheduled_start_datetime, scheduled_end_datetime,
    source_file, source_row_num
)
-- DISTINCT ON keeps the first row of each (employee, punch-in) group in
-- ORDER BY order, i.e. the copy from the latest extract.
SELECT DISTINCT ON (client_employee_id, punch_in_datetime) *
FROM (
    SELECT
        silver.clean_text(client_employee_id)                   AS client_employee_id,
        silver.clean_text(department_id)                        AS department_id,
        silver.clean_text(department_name)                      AS department_name,
        silver.clean_text(home_department_id)                   AS home_department_id,
        silver.clean_text(home_department_name)                 AS home_department_name,
        silver.clean_text(pay_code)                             AS pay_code,
        silver.clean_text(punch_in_comment)                     AS punch_in_comment,
        silver.clean_text(punch_out_comment)                    AS punch_out_comment,
        silver.clean_text(hours_worked)::NUMERIC(5,2)           AS hours_worked,
        silver.clean_text(punch_apply_date)::DATE               AS punch_apply_date,
        silver.clean_text(punch_in_datetime)::TIMESTAMP         AS punch_in_datetime,
        silver.clean_text(punch_out_datetime)::TIMESTAMP        AS punch_out_datetime,
        silver.clean_text(scheduled_start_datetime)::TIMESTAMP  AS scheduled_start_datetime,
        silver.clean_text(scheduled_end_datetime)::TIMESTAMP    AS scheduled_end_datetime,
        source_file,
        source_row_num
    FROM bronze.timesheet_raw
) AS cleaned
-- "Latest extract wins" relies on the file names sorting by extraction time:
-- they all follow timesheet_YYYYMMDDHHMM.csv, so source_file DESC = newest
-- first. A file named any other way would silently break this ordering.
ORDER BY client_employee_id, punch_in_datetime, source_file DESC;
