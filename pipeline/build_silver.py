"""
Build the silver layer from bronze with set-based SQL inside Postgres.

The SQL lives in pipeline/sql/ (one script per silver table); this module runs
each script in its own transaction, logs row counts so every run shows how
many rows were rejected and how many duplicates were removed, and writes the
same counts to silver.cleaning_log.

silver.timesheet loads incrementally by default (the last INCREMENTAL_WINDOW_DAYS
before the latest punch date are reloaded) or fully with --full-reload.
silver.employee is upserted by default, keeping API changes; --full-reload
truncates it first, resetting it to the file.

Run from the project root:  python -m pipeline.build_silver [--full-reload]
"""

import argparse
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from pipeline.db import get_connection

logger = logging.getLogger(__name__)

SQL_DIR = Path(__file__).parent / "sql"


def count_rows(cur, table: str) -> int:
    # Table names are fixed strings from this module, never user input.
    cur.execute(f"SELECT count(*) FROM {table}")
    return cur.fetchone()[0]


def fetch_counts(*queries: str) -> list[int]:
    """Run count queries on the committed silver data."""
    counts = []
    conn = get_connection()
    try:
        with conn, conn.cursor() as cur:
            for query in queries:
                cur.execute(query)
                counts.append(cur.fetchone()[0])
    finally:
        conn.close()
    return counts


def manual_run_id() -> str:
    # Same shape as Airflow's run_id, for runs outside Airflow.
    return f"manual__{datetime.now(timezone.utc).isoformat(timespec='seconds')}"


def get_window_start(cur):
    """Course watermark pattern: latest date already loaded, read from the target table."""
    # On an empty table the 2000-01-01 default makes the incremental run load everything.
    cur.execute(
        "SELECT MAX(punch_apply_date), "
        "COALESCE(MAX(punch_apply_date) - %s, DATE '2000-01-01') FROM silver.timesheet",
        (int(os.environ["INCREMENTAL_WINDOW_DAYS"]),),
    )
    watermark, window_start = cur.fetchone()
    logger.info(f"Watermark: {watermark}, window start: {window_start}")
    return window_start


def write_cleaning_log(cur, run_id, table, load_mode, window_start, read, rejected, outside, loaded) -> int:
    """Insert this build's cleaning_log row and return the duplicates count."""
    duplicates = read - rejected - outside - loaded
    # Same transaction as the data: a log row exists only if the data was committed.
    cur.execute(
        "INSERT INTO silver.cleaning_log (run_id, table_name, load_mode, window_start, rows_read, "
        "rows_rejected, rows_outside_window, rows_duplicate, rows_loaded) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (run_id, table, load_mode, window_start, read, rejected, outside, duplicates, loaded),
    )
    logger.info(
        f"{table} ({load_mode}): {read:,} read | {rejected:,} rejected | "
        f"{outside:,} outside window | {duplicates:,} duplicates removed | {loaded:,} loaded"
    )
    return duplicates


def build_silver_timesheet(run_id: str | None = None, full_reload: bool = False) -> int:
    """Load silver.timesheet; returns the rows loaded by this run."""
    load_mode = "full" if full_reload else "incremental"
    sql = (SQL_DIR / "silver_timesheet.sql").read_text(encoding="utf-8")
    conn = get_connection()
    try:
        # Commits on success, rolls back on any error.
        with conn, conn.cursor() as cur:
            if full_reload:
                cur.execute("TRUNCATE silver.timesheet")
                window_start = None  # no window: the script loads every row
            else:
                window_start = get_window_start(cur)

            read = count_rows(cur, "bronze.timesheet_raw")
            cur.execute(sql, {"window_start": window_start})
            # Counted, not rowcount: the script has several statements.
            rejected = count_rows(cur, "silver.timesheet_rejects")
            # Valid rows dated before the window: already in silver, left as they are.
            cur.execute(
                "SELECT count(*) FROM checked_timesheet "
                "WHERE reject_reason IS NULL AND apply_date < %s",
                (window_start,),
            )
            outside = cur.fetchone()[0]
            cur.execute(
                "SELECT count(*) FROM silver.timesheet "
                "WHERE %(ws)s::DATE IS NULL OR punch_apply_date >= %(ws)s",
                {"ws": window_start},
            )
            loaded = cur.fetchone()[0]
            write_cleaning_log(
                cur, run_id or manual_run_id(), "silver.timesheet", load_mode,
                window_start, read, rejected, outside, loaded,
            )
    finally:
        conn.close()

    # Compare each silver row with its bronze row (joined by lineage).
    total, nulled, over_24, scheduled, incomplete = fetch_counts(
        "SELECT count(*) FROM silver.timesheet",
        """SELECT count(*) FROM silver.timesheet s
           JOIN bronze.timesheet_raw b USING (source_file, source_row_num)
           WHERE s.department_name IS NULL
             AND silver.clean_text(b.department_name) IS NOT NULL""",
        "SELECT count(*) FROM silver.timesheet WHERE hours_worked > 24",
        "SELECT count(*) FROM silver.timesheet WHERE has_schedule",
        "SELECT count(*) FROM silver.timesheet WHERE is_incomplete",
    )
    logger.info(f"silver.timesheet: {total:,} rows in total")
    logger.info(f"silver.timesheet: {nulled:,} department placeholder names set to NULL")
    logger.info(f"silver.timesheet: {scheduled:,} rows with a schedule ({scheduled / total:.1%})")
    logger.info(f"silver.timesheet: {incomplete:,} incomplete rows (punch-out after export)")
    if over_24:
        logger.warning(f"silver.timesheet: {over_24:,} rows with hours_worked > 24 (kept)")
    return loaded


def build_silver_employee(run_id: str | None = None, full_reload: bool = False) -> int:
    """Upsert silver.employee from the file; returns the employees in the file."""
    load_mode = "full" if full_reload else "incremental"
    sql = (SQL_DIR / "silver_employee.sql").read_text(encoding="utf-8")
    conn = get_connection()
    try:
        with conn, conn.cursor() as cur:
            if full_reload:
                cur.execute("TRUNCATE silver.employee")

            read = count_rows(cur, "bronze.employee_raw")
            cur.execute(sql)
            rejected = count_rows(cur, "silver.employee_rejects")
            # Counted from the file, not the table: API rows live there too.
            cur.execute(
                "SELECT count(DISTINCT silver.clean_text(client_employee_id)) "
                "FROM checked_employee WHERE reject_reason IS NULL"
            )
            loaded = cur.fetchone()[0]
            # now() is the transaction start, so this finds rows written by this run.
            cur.execute("SELECT count(*) FROM silver.employee WHERE loaded_at = now()")
            upserted = cur.fetchone()[0]
            # File rows only, so API edits to department_name aren't counted.
            cur.execute(
                "SELECT count(*) FROM checked_employee WHERE reject_reason IS NULL "
                "AND left(silver.clean_text(department_name), length(silver.clean_text(department_id)) + 1) "
                "= silver.clean_text(department_id) || '-'"
            )
            stripped = cur.fetchone()[0]
            write_cleaning_log(
                cur, run_id or manual_run_id(), "silver.employee", load_mode,
                None, read, rejected, 0, loaded,
            )
    finally:
        conn.close()

    per_diem, api_rows = fetch_counts(
        "SELECT count(*) FROM silver.employee WHERE is_per_diem",
        "SELECT count(*) FROM silver.employee WHERE source_file = 'api'",
    )
    logger.info(f"silver.employee: {upserted:,} inserted or updated, {loaded - upserted:,} unchanged")
    logger.info(f"silver.employee: {api_rows:,} API-owned rows kept")
    logger.info(f"silver.employee: {stripped:,} department ID prefixes stripped")
    logger.info(f"silver.employee: {per_diem:,} employees marked per diem")
    return loaded


def parse_args():
    parser = argparse.ArgumentParser(description="Build the silver layer")
    parser.add_argument(
        "--full-reload",
        action="store_true",
        help="Truncate and reload the silver tables (default: incremental)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)s [%(filename)s:%(lineno)d] %(message)s",
    )
    args = parse_args()
    run_id = manual_run_id()  # one ID for both tables in this run
    build_silver_timesheet(run_id, full_reload=args.full_reload)
    build_silver_employee(run_id, full_reload=args.full_reload)
