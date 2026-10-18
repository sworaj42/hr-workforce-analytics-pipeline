"""
Build the gold star schema from silver (course Week4 etl.py structure: one
load function per table, called in order).

Silver and gold share a database, so each load is one INSERT ... SELECT.
The fact loads incrementally by default, or fully with --full-reload.

Run from the project root:  python -m pipeline.build_gold [--full-reload]
"""

import argparse
import logging
import os

from pipeline.db import get_connection

logger = logging.getLogger(__name__)


def load_dim_date(conn):
    # Course dim_date, covering every year that any punch, hire or termination falls in.
    insert_dim_date_sql = """
    WITH bounds AS (
        SELECT min(d) AS first_day, max(d) AS last_day
        FROM (
            SELECT punch_apply_date AS d FROM silver.timesheet
            UNION ALL SELECT hire_date        FROM silver.employee
            UNION ALL SELECT recent_hire_date FROM silver.employee
            UNION ALL SELECT term_date        FROM silver.employee
        ) AS all_dates
    )
    INSERT INTO gold.dim_date (
        date_key, full_date, year, quarter, month,
        month_name, week_of_year, day_of_week, day_name, is_weekend
    )
    SELECT
        TO_CHAR(d, 'YYYYMMDD')::INTEGER     AS date_key,
        d::DATE                             AS full_date,
        EXTRACT(YEAR    FROM d)::SMALLINT   AS year,
        EXTRACT(QUARTER FROM d)::SMALLINT   AS quarter,
        EXTRACT(MONTH   FROM d)::SMALLINT   AS month,
        TRIM(TO_CHAR(d, 'Month'))           AS month_name,   -- trim trailing spaces!
        EXTRACT(WEEK    FROM d)::SMALLINT   AS week_of_year,
        EXTRACT(DOW     FROM d)::SMALLINT   AS day_of_week,  -- 0=Sun, 6=Sat
        TRIM(TO_CHAR(d, 'Day'))             AS day_name,     -- trim trailing spaces!
        EXTRACT(DOW FROM d) IN (0, 6)       AS is_weekend
    FROM bounds,
         generate_series(date_trunc('year', first_day),
                         date_trunc('year', last_day) + INTERVAL '1 year - 1 day',
                         INTERVAL '1 day') AS d
    ON CONFLICT (date_key) DO NOTHING
    """
    try:
        with conn.cursor() as curr:
            curr.execute(insert_dim_date_sql)
            logger.info(f"{curr.rowcount} inserted to gold.dim_date")
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(str(e))
        raise


def load_dim_department(conn):
    # One row per department ID, named from the latest file.
    upsert_dim_department_sql = """
    INSERT INTO gold.dim_department (department_id, department_name, department_label)
    SELECT DISTINCT ON (department_id)
        department_id,
        department_name,
        COALESCE(department_name || ' (' || department_id || ')', department_id)
    FROM (
        SELECT department_id, department_name, source_file FROM silver.timesheet
        UNION ALL
        SELECT home_department_id, home_department_name, source_file FROM silver.timesheet
        UNION ALL
        SELECT department_id, department_name, source_file FROM silver.employee
    ) AS all_departments
    WHERE department_id IS NOT NULL
    ORDER BY department_id, department_name IS NULL, substring(source_file FROM '[0-9]{12}') DESC
    ON CONFLICT (department_id) DO UPDATE SET
        department_name  = EXCLUDED.department_name,
        department_label = EXCLUDED.department_label,
        loaded_at        = now()
    """
    try:
        with conn.cursor() as curr:
            curr.execute(upsert_dim_department_sql)
            logger.info(f"{curr.rowcount} inserted or updated in gold.dim_department")
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(str(e))
        raise


def load_dim_employee(conn):
    # SCD Type 1: new employees are added, existing ones overwritten.
    # DO UPDATE also turns an inferred row into a real one, keeping its key.
    upsert_dim_employee_sql = """
    INSERT INTO gold.dim_employee (
        client_employee_id, first_name, job_code, job_title, job_start_date,
        organization_name, department_id, department_name, fte_status,
        scheduled_weekly_hour, manager_employee_id, hire_date, recent_hire_date,
        term_date, active_status, termination_reason, is_per_diem,
        is_inferred, source_file, source_row_num
    )
    SELECT
        client_employee_id, first_name, job_code, job_title, job_start_date,
        organization_name, department_id, department_name, fte_status,
        scheduled_weekly_hour, manager_employee_id, hire_date, recent_hire_date,
        term_date, active_status, termination_reason, is_per_diem,
        false, source_file, source_row_num
    FROM silver.employee
    ON CONFLICT (client_employee_id) DO UPDATE SET
        first_name            = EXCLUDED.first_name,
        job_code              = EXCLUDED.job_code,
        job_title             = EXCLUDED.job_title,
        job_start_date        = EXCLUDED.job_start_date,
        organization_name     = EXCLUDED.organization_name,
        department_id         = EXCLUDED.department_id,
        department_name       = EXCLUDED.department_name,
        fte_status            = EXCLUDED.fte_status,
        scheduled_weekly_hour = EXCLUDED.scheduled_weekly_hour,
        manager_employee_id   = EXCLUDED.manager_employee_id,
        hire_date             = EXCLUDED.hire_date,
        recent_hire_date      = EXCLUDED.recent_hire_date,
        term_date             = EXCLUDED.term_date,
        active_status         = EXCLUDED.active_status,
        termination_reason    = EXCLUDED.termination_reason,
        is_per_diem           = EXCLUDED.is_per_diem,
        is_inferred           = EXCLUDED.is_inferred,
        source_file           = EXCLUDED.source_file,
        source_row_num        = EXCLUDED.source_row_num,
        loaded_at             = now()
    """
    try:
        with conn.cursor() as curr:
            curr.execute(upsert_dim_employee_sql)
            logger.info(f"{curr.rowcount} inserted or updated in gold.dim_employee")
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(str(e))
        raise


def load_inferred_employees(conn):
    # Timesheet employees missing from the employee file get an ID-only row, so no punch is dropped.
    insert_inferred_sql = """
    INSERT INTO gold.dim_employee (client_employee_id, is_inferred)
    SELECT DISTINCT t.client_employee_id, true
    FROM silver.timesheet AS t
    WHERE NOT EXISTS (
        SELECT 1 FROM gold.dim_employee AS d
        WHERE d.client_employee_id = t.client_employee_id
    )
    """
    try:
        with conn.cursor() as curr:
            curr.execute(insert_inferred_sql)
            logger.info(f"{curr.rowcount} inferred employees inserted to gold.dim_employee")
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(str(e))
        raise


def load_fact_timesheet(conn, full_reload=False):
    # Same window as silver: reload punches from window_start; a full reload truncates first.
    insert_fact_timesheet_sql = """
    INSERT INTO gold.fact_timesheet (
        employee_key, date_key, department_key, home_department_key,
        client_employee_id, pay_code, punch_in_comment, punch_out_comment,
        hours_worked, punch_apply_date, punch_in_datetime, punch_out_datetime,
        scheduled_start_datetime, scheduled_end_datetime,
        has_schedule, is_incomplete, is_worked, source_file, source_row_num
    )
    SELECT
        e.employee_key,
        TO_CHAR(t.punch_apply_date, 'YYYYMMDD')::INTEGER AS date_key,
        d.department_key,
        h.department_key AS home_department_key,
        t.client_employee_id, t.pay_code, t.punch_in_comment, t.punch_out_comment,
        t.hours_worked, t.punch_apply_date, t.punch_in_datetime, t.punch_out_datetime,
        t.scheduled_start_datetime, t.scheduled_end_datetime,
        t.has_schedule, t.is_incomplete,
        -- A midnight entry is a booking, unless it's a regular shift code.
        NOT (
            t.punch_in_datetime::time = '00:00:00'
            AND COALESCE(t.pay_code, '') NOT IN ('Hourly', 'Exempt', 'normal_worked', 'Per Diem')
        ) AS is_worked,
        t.source_file, t.source_row_num
    FROM silver.timesheet AS t
    JOIN gold.dim_employee AS e USING (client_employee_id)
    LEFT JOIN gold.dim_department AS d ON d.department_id = t.department_id
    LEFT JOIN gold.dim_department AS h ON h.department_id = t.home_department_id
    WHERE %(window_start)s::DATE IS NULL OR t.punch_apply_date >= %(window_start)s
    """
    try:
        with conn.cursor() as curr:
            if full_reload:
                curr.execute("TRUNCATE gold.fact_timesheet")
                window_start = None
                logger.info("Full reload: gold.fact_timesheet truncated")
            else:
                # Course watermark pattern, read from the target table.
                curr.execute(
                    "SELECT MAX(punch_apply_date), "
                    "COALESCE(MAX(punch_apply_date) - %s, DATE '2000-01-01') FROM gold.fact_timesheet",
                    (int(os.environ["INCREMENTAL_WINDOW_DAYS"]),),
                )
                watermark, window_start = curr.fetchone()
                logger.info(f"Watermark: {watermark}, window start: {window_start}")
                curr.execute(
                    "DELETE FROM gold.fact_timesheet WHERE punch_apply_date >= %s", (window_start,)
                )
                logger.info(f"{curr.rowcount} deleted from gold.fact_timesheet")
            curr.execute(insert_fact_timesheet_sql, {"window_start": window_start})
            logger.info(f"{curr.rowcount} inserted to gold.fact_timesheet")
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(str(e))
        raise


def build_gold(full_reload=False):
    """Load the dimensions first, then the fact that references them."""
    conn = get_connection()
    try:
        load_dim_date(conn)
        load_dim_department(conn)
        load_dim_employee(conn)        # real employees before inferred ones,
        load_inferred_employees(conn)  # so an ID in both files becomes real
        load_fact_timesheet(conn, full_reload)
    finally:
        conn.close()


def parse_args():
    parser = argparse.ArgumentParser(description="Build the gold layer")
    parser.add_argument(
        "--full-reload",
        action="store_true",
        help="Truncate and reload gold.fact_timesheet (default: incremental)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)s [%(filename)s:%(lineno)d] %(message)s",
    )
    build_gold(parse_args().full_reload)
