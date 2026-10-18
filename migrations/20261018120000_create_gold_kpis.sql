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
CREATE OR REPLACE VIEW gold.kpi_turnover_monthly AS
WITH months AS (
    SELECT
        full_date AS month_start,
        LEAST((full_date + INTERVAL '1 month - 1 day')::DATE,
              (SELECT MAX(as_of_date) FROM gold.kpi_active_headcount)) AS month_end
    FROM gold.dim_date
    WHERE full_date = date_trunc('month', full_date)::DATE                               -- first day of each month
      AND full_date >= (SELECT date_trunc('month', MIN(term_date)) FROM gold.dim_employee) -- file has no earlier leavers
      AND full_date <= (SELECT MAX(as_of_date) FROM gold.kpi_active_headcount)
),
terminations AS (
    SELECT
        date_trunc('month', term_date)::DATE AS month_start,
        COUNT(*) AS terminations,
        COUNT(*) FILTER (WHERE termination_reason = 'Terminate_Employee_Voluntary')   AS voluntary,
        COUNT(*) FILTER (WHERE termination_reason = 'Terminate_Employee_Involuntary') AS involuntary
    FROM gold.dim_employee
    WHERE term_date IS NOT NULL
    GROUP BY 1
)
SELECT
    m.month_start,
    COALESCE(t.terminations, 0) AS terminations,
    COALESCE(t.voluntary, 0)    AS voluntary,
    COALESCE(t.involuntary, 0)  AS involuntary,
    hs.active_count             AS start_headcount,
    he.active_count             AS end_headcount,
    -- terminations / average headcount
    ROUND(100.0 * COALESCE(t.terminations, 0)
          / NULLIF((hs.active_count + he.active_count) / 2.0, 0), 2) AS turnover_rate_pct
FROM months AS m
LEFT JOIN terminations AS t USING (month_start)
JOIN gold.kpi_active_headcount AS hs ON hs.as_of_date = m.month_start
JOIN gold.kpi_active_headcount AS he ON he.as_of_date = m.month_end;
