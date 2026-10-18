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
WHERE d.full_date <= DATE '2025-10-16'                        -- employee file export date
GROUP BY d.full_date;
