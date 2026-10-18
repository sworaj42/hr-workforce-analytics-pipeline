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
