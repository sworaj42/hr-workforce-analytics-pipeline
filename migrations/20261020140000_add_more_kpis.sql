-- More KPI views: attendance and hours by department, double shifts.

-- Late arrivals, early departures and overtime per department (same rules as the attendance KPIs).
CREATE OR REPLACE VIEW gold.kpi_attendance_by_department AS
SELECT
    COALESCE(d.department_label, 'No department')  AS department,
    COUNT(*)                                       AS scheduled_shifts,
    COUNT(*) FILTER (
        WHERE f.punch_in_datetime > f.scheduled_start_datetime + INTERVAL '5 minutes'
    )                                              AS late_arrivals,
    ROUND(COUNT(*) FILTER (
        WHERE f.punch_in_datetime > f.scheduled_start_datetime + INTERVAL '5 minutes'
    ) * 100.0 / COUNT(*), 1)                       AS late_pct,
    COUNT(*) FILTER (
        WHERE f.punch_out_datetime < f.scheduled_end_datetime - INTERVAL '5 minutes'
    )                                              AS early_departures,
    -- Worked more than 5 minutes beyond the scheduled shift length.
    COUNT(*) FILTER (
        WHERE (f.punch_out_datetime - f.punch_in_datetime)
            - (f.scheduled_end_datetime - f.scheduled_start_datetime) > INTERVAL '5 minutes'
    )                                              AS overtime_shifts
FROM gold.fact_timesheet AS f
LEFT JOIN gold.dim_department AS d ON d.department_key = f.department_key
WHERE f.has_schedule          -- needs a schedule
  AND NOT f.is_incomplete     -- only finished shifts
  AND f.is_worked             -- only clocked work
GROUP BY 1;

-- Worked hours per department.
CREATE OR REPLACE VIEW gold.kpi_hours_by_department AS
WITH daily AS (
    -- One employee can have several punches in a day, so sum them first.
    SELECT department_key, employee_key, punch_apply_date, SUM(hours_worked) AS daily_hours
    FROM gold.fact_timesheet
    WHERE NOT is_incomplete AND is_worked
    GROUP BY department_key, employee_key, punch_apply_date
)
SELECT
    COALESCE(d.department_label, 'No department')  AS department,
    COUNT(DISTINCT w.employee_key)                 AS employees,
    ROUND(SUM(w.daily_hours), 0)                   AS total_hours,
    ROUND(AVG(w.daily_hours), 2)                   AS avg_hours_per_employee_day
FROM daily AS w
LEFT JOIN gold.dim_department AS d ON d.department_key = w.department_key
GROUP BY 1;

-- Double shifts (more than 16 worked hours) per month.
CREATE OR REPLACE VIEW gold.kpi_long_shifts AS
SELECT
    date_trunc('month', punch_apply_date)::date              AS month,
    COUNT(*)                                                 AS worked_shifts,
    COUNT(*) FILTER (WHERE hours_worked > 16)                AS double_shifts,
    ROUND(COUNT(*) FILTER (WHERE hours_worked > 16) * 100.0
          / COUNT(*), 2)                                     AS double_shift_pct
FROM gold.fact_timesheet
WHERE NOT is_incomplete AND is_worked
GROUP BY 1;
