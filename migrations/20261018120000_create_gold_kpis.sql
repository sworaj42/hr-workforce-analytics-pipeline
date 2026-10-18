-- KPI views on the gold star schema.

-- Active headcount on each date (real employees only).
CREATE OR REPLACE VIEW gold.kpi_active_headcount AS
SELECT
    d.full_date            AS as_of_date,
    COUNT(e.employee_key)  AS active_count
FROM gold.dim_date AS d
LEFT JOIN gold.dim_employee AS e
    ON  e.is_inferred = false                                 -- real employees only
    AND e.recent_hire_date <= d.full_date                     -- already hired on this date
    AND (e.term_date IS NULL OR e.term_date >= d.full_date)   -- termination day counts as active
WHERE d.full_date <= (SELECT MAX(punch_apply_date) FROM gold.fact_timesheet)  -- latest date in the data
GROUP BY d.full_date;

-- Terminations and turnover rate per month (real employees only).
CREATE OR REPLACE VIEW gold.kpi_turnover_trend AS
WITH months AS (
    -- First day of each month, same range as headcount.
    SELECT full_date AS month
    FROM gold.dim_date
    WHERE full_date = date_trunc('month', full_date)
      AND full_date >= (SELECT date_trunc('month', MIN(term_date))
                        FROM gold.dim_employee WHERE NOT is_inferred)
      AND full_date <= (SELECT MAX(punch_apply_date) FROM gold.fact_timesheet)
),
terms AS (
    -- Terminations per month; exact reasons, since 'Involuntary' contains 'voluntary'.
    SELECT
        date_trunc('month', term_date)::date                                          AS month,
        COUNT(*)                                                                      AS terminations,
        COUNT(*) FILTER (WHERE termination_reason = 'Terminate_Employee_Voluntary')   AS voluntary,
        COUNT(*) FILTER (WHERE termination_reason = 'Terminate_Employee_Involuntary') AS involuntary
    FROM gold.dim_employee
    WHERE NOT is_inferred
      AND term_date IS NOT NULL
    GROUP BY 1
)
SELECT
    m.month,
    COALESCE(t.terminations, 0)  AS terminations,
    COALESCE(t.voluntary, 0)     AS voluntary,
    COALESCE(t.involuntary, 0)   AS involuntary,
    h.active_count               AS headcount_start,
    ROUND(COALESCE(t.terminations, 0) * 100.0 / NULLIF(h.active_count, 0), 1) AS turnover_rate_pct
FROM months AS m
LEFT JOIN terms AS t                     ON t.month = m.month
LEFT JOIN gold.kpi_active_headcount AS h ON h.as_of_date = m.month;

-- Average tenure per department (real employees, current staff and leavers).
CREATE OR REPLACE VIEW gold.kpi_avg_tenure_by_department AS
SELECT
    department_id,
    department_name,
    COUNT(*)  AS employees,
    -- Leavers: hire to termination. Active staff: hire to the last day of data.
    ROUND(AVG(
        COALESCE(term_date, (SELECT MAX(punch_apply_date) FROM gold.fact_timesheet))
        - recent_hire_date
    ) / 365, 1)  AS avg_tenure_years
FROM gold.dim_employee
WHERE NOT is_inferred                         -- real employees only
GROUP BY department_id, department_name;

-- Share of employees who left within 90 days of their most recent hire (one row).
CREATE OR REPLACE VIEW gold.kpi_early_attrition_rate AS
SELECT
    90                                                         AS window_days,    -- "early" = within 90 days of hire
    COUNT(*)                                                   AS employees,
    COUNT(*) FILTER (WHERE term_date - recent_hire_date <= 90) AS early_leavers,
    ROUND(
        COUNT(*) FILTER (WHERE term_date - recent_hire_date <= 90)
        * 100.0 / NULLIF(COUNT(*), 0)
    , 1)                                                       AS early_attrition_rate_pct
FROM gold.dim_employee
WHERE NOT is_inferred;                                          -- real employees only

-- Average worked hours per employee per day worked.
CREATE OR REPLACE VIEW gold.kpi_avg_working_hours AS
WITH daily AS (
    -- One employee can have several punches in a day, so sum them first.
    SELECT employee_key, punch_apply_date, SUM(hours_worked) AS daily_hours
    FROM gold.fact_timesheet
    WHERE NOT is_incomplete AND is_worked
    GROUP BY employee_key, punch_apply_date
)
SELECT
    e.client_employee_id,
    e.is_inferred,
    COUNT(*)                      AS days_worked,
    ROUND(AVG(d.daily_hours), 2)  AS avg_daily_hours
FROM daily AS d
JOIN gold.dim_employee AS e ON e.employee_key = d.employee_key
GROUP BY e.client_employee_id, e.is_inferred;

-- Daily average worked hours per employee, with a 7-day rolling average.
CREATE OR REPLACE VIEW gold.kpi_rolling_avg_working_hours AS
WITH employee_day AS (
    -- Worked hours per employee per day (same rule as kpi_avg_working_hours).
    SELECT employee_key, punch_apply_date, SUM(hours_worked) AS daily_hours
    FROM gold.fact_timesheet
    WHERE NOT is_incomplete AND is_worked
    GROUP BY employee_key, punch_apply_date
),
daily AS (
    -- One row per day: how many worked, total and average hours.
    SELECT
        punch_apply_date  AS work_date,
        COUNT(*)          AS employees_working,
        SUM(daily_hours)  AS total_hours,
        AVG(daily_hours)  AS avg_hours_per_employee
    FROM employee_day
    GROUP BY punch_apply_date
)
SELECT
    work_date,
    employees_working,
    ROUND(avg_hours_per_employee, 2)  AS avg_hours_per_employee,
    -- Worked hours / employees over this day and the 6 calendar days before it.
    ROUND(SUM(total_hours) OVER w / SUM(employees_working) OVER w, 2)  AS rolling_7d_avg_hours
FROM daily
WINDOW w AS (ORDER BY work_date RANGE BETWEEN INTERVAL '6 days' PRECEDING AND CURRENT ROW);

-- Late arrivals per employee: clocked in more than 5 minutes after the scheduled start.
CREATE OR REPLACE VIEW gold.kpi_late_arrivals AS
SELECT
    e.client_employee_id,
    e.is_inferred,
    COUNT(*)  AS scheduled_shifts,
    COUNT(*) FILTER (
        WHERE f.punch_in_datetime > f.scheduled_start_datetime + INTERVAL '5 minutes'
    )         AS late_arrivals,
    ROUND(COUNT(*) FILTER (
        WHERE f.punch_in_datetime > f.scheduled_start_datetime + INTERVAL '5 minutes'
    ) * 100.0 / COUNT(*), 1)  AS late_rate_pct
FROM gold.fact_timesheet AS f
JOIN gold.dim_employee AS e ON e.employee_key = f.employee_key
WHERE f.has_schedule          -- needs a scheduled start
  AND NOT f.is_incomplete     -- only finished shifts
  AND f.is_worked             -- only clocked work
GROUP BY e.client_employee_id, e.is_inferred;

-- Early departure days per employee: clocked out more than 5 minutes before the scheduled end.
CREATE OR REPLACE VIEW gold.kpi_early_departures AS
SELECT
    e.client_employee_id,
    e.is_inferred,
    COUNT(DISTINCT f.punch_apply_date)  AS scheduled_days,
    COUNT(DISTINCT f.punch_apply_date) FILTER (
        WHERE f.punch_out_datetime < f.scheduled_end_datetime - INTERVAL '5 minutes'
    )                                   AS early_departure_days
FROM gold.fact_timesheet AS f
JOIN gold.dim_employee AS e ON e.employee_key = f.employee_key
WHERE f.has_schedule          -- needs a scheduled end
  AND NOT f.is_incomplete     -- only finished shifts
  AND f.is_worked             -- only clocked work
GROUP BY e.client_employee_id, e.is_inferred;

-- Overtime per employee: worked more than 5 minutes beyond the scheduled shift length.
CREATE OR REPLACE VIEW gold.kpi_overtime AS
WITH shifts AS (
    -- Minutes worked beyond the scheduled length of each shift.
    SELECT
        employee_key,
        punch_apply_date,
        EXTRACT(EPOCH FROM (punch_out_datetime - punch_in_datetime)
                         - (scheduled_end_datetime - scheduled_start_datetime)) / 60  AS extra_minutes
    FROM gold.fact_timesheet
    WHERE has_schedule AND NOT is_incomplete AND is_worked
)
SELECT
    e.client_employee_id,
    e.is_inferred,
    COUNT(DISTINCT s.punch_apply_date)                                     AS scheduled_days,
    COUNT(DISTINCT s.punch_apply_date) FILTER (WHERE s.extra_minutes > 5)  AS overtime_days,
    ROUND(COALESCE(SUM(s.extra_minutes) FILTER (WHERE s.extra_minutes > 5), 0) / 60, 2)  AS overtime_hours
FROM shifts AS s
JOIN gold.dim_employee AS e ON e.employee_key = s.employee_key
GROUP BY e.client_employee_id, e.is_inferred;
