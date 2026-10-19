-- Results of the data quality checks run after each gold build (pipeline/quality.py).

-- One row per check per run. Append-only and no primary key, like
-- silver.cleaning_log: a retried task adds rows instead of failing.
CREATE TABLE IF NOT EXISTS gold.dq_results (
    run_id      TEXT          NOT NULL,  -- Airflow run_id, or manual__<time>
    check_name  TEXT          NOT NULL,
    passed      BOOLEAN       NOT NULL,
    detail      TEXT,                    -- the numbers behind the result
    checked_at  TIMESTAMPTZ   NOT NULL DEFAULT now()
);
