-- Soft delete for employees, set by the API.

ALTER TABLE silver.employee
    ADD COLUMN is_deleted BOOLEAN NOT NULL DEFAULT false,  -- soft delete, set by the API
    ALTER COLUMN source_row_num DROP NOT NULL;             -- API-created rows have no file row

ALTER TABLE gold.dim_employee
    ADD COLUMN is_deleted BOOLEAN NOT NULL DEFAULT false;

-- HR KPIs leave out deleted employees; attendance KPIs keep their punches.

CREATE OR REPLACE VIEW gold.kpi_active_headcount AS
SELECT
    d.full_date            AS as_of_date,
    COUNT(e.employee_key)  AS active_count
FROM gold.dim_date AS d
LEFT JOIN gold.dim_employee AS e
    ON  e.is_inferred = false                                 -- real employees only
    AND NOT e.is_deleted                                      -- deleted records don't count
    AND e.recent_hire_date <= d.full_date                     -- already hired on this date
    AND (e.term_date IS NULL OR e.term_date >= d.full_date)   -- termination day counts as active
WHERE d.full_date <= (SELECT MAX(punch_apply_date) FROM gold.fact_timesheet)  -- latest date in the data
GROUP BY d.full_date;

CREATE OR REPLACE VIEW gold.kpi_turnover_trend AS
WITH months AS (
    -- First day of each month, same range as headcount.
    SELECT full_date AS month
    FROM gold.dim_date
    WHERE full_date = date_trunc('month', full_date)
      AND full_date >= (SELECT date_trunc('month', MIN(term_date))
                        FROM gold.dim_employee WHERE NOT is_inferred AND NOT is_deleted)
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
      AND NOT is_deleted
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
  AND NOT is_deleted
GROUP BY department_id, department_name;

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
WHERE NOT is_inferred                                           -- real employees only
  AND NOT is_deleted;
