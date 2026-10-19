-- Indexes on punch_apply_date, the column the API and the incremental window filter on.

-- GET /timesheets date range; silver window delete and the gold insert's read.
CREATE INDEX IF NOT EXISTS ix_timesheet_punch_apply_date
    ON silver.timesheet (punch_apply_date);

-- Gold window delete.
CREATE INDEX IF NOT EXISTS ix_fact_timesheet_punch_apply_date
    ON gold.fact_timesheet (punch_apply_date);
