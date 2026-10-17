"""
Build the silver layer from bronze with set-based SQL inside Postgres.

The SQL lives in pipeline/sql/ (one rebuild script per silver table); this
module runs each script in its own transaction, logs row counts so every
run shows how many rows were rejected and how many duplicates were removed,
and writes the same counts to silver.cleaning_log.

Run from the project root:  python -m pipeline.build_silver
"""

import logging
from datetime import datetime, timezone
from pathlib import Path

from pipeline.db import get_connection

logger = logging.getLogger(__name__)

SQL_DIR = Path(__file__).parent / "sql"

LOAD_MODE = "full"  # the incremental mode is added later


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


def rebuild_silver_table(sql_file: str, bronze_table: str, silver_table: str, run_id: str) -> int:
    """Run one rebuild script from pipeline/sql/. Returns the number of rows loaded."""
    sql = (SQL_DIR / sql_file).read_text(encoding="utf-8")
    conn = get_connection()
    try:
        # Commits on success, rolls back on any error.
        with conn, conn.cursor() as cur:
            read = count_rows(cur, bronze_table)
            cur.execute(sql)
            # Counted, not rowcount: the script has several statements.
            rejected = count_rows(cur, f"{silver_table}_rejects")
            loaded = count_rows(cur, silver_table)
            duplicates = read - rejected - loaded
            # Same transaction as the data: a log row exists only if the data was committed.
            cur.execute(
                "INSERT INTO silver.cleaning_log "
                "(run_id, table_name, load_mode, rows_read, rows_rejected, rows_duplicate, rows_loaded) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (run_id, silver_table, LOAD_MODE, read, rejected, duplicates, loaded),
            )
    finally:
        conn.close()

    logger.info(
        f"{silver_table}: {read:,} read | {rejected:,} rejected | "
        f"{duplicates:,} duplicates removed | {loaded:,} loaded"
    )
    return loaded


def build_silver_timesheet(run_id: str | None = None) -> int:
    loaded = rebuild_silver_table(
        "silver_timesheet.sql", "bronze.timesheet_raw", "silver.timesheet", run_id or manual_run_id()
    )
    # Compare each silver row with its bronze row (joined by lineage).
    nulled, over_24 = fetch_counts(
        """SELECT count(*) FROM silver.timesheet s
           JOIN bronze.timesheet_raw b USING (source_file, source_row_num)
           WHERE s.department_name IS NULL
             AND silver.clean_text(b.department_name) IS NOT NULL""",
        "SELECT count(*) FROM silver.timesheet WHERE hours_worked > 24",
    )
    logger.info(f"silver.timesheet: {nulled:,} department placeholder names set to NULL")
    if over_24:
        logger.warning(f"silver.timesheet: {over_24:,} rows with hours_worked > 24 (kept)")
    return loaded


def build_silver_employee(run_id: str | None = None) -> int:
    loaded = rebuild_silver_table(
        "silver_employee.sql", "bronze.employee_raw", "silver.employee", run_id or manual_run_id()
    )
    stripped, per_diem = fetch_counts(
        """SELECT count(*) FROM silver.employee s
           JOIN bronze.employee_raw b USING (source_file, source_row_num)
           WHERE s.department_name <> silver.clean_text(b.department_name)""",
        "SELECT count(*) FROM silver.employee WHERE is_per_diem",
    )
    logger.info(f"silver.employee: {stripped:,} department ID prefixes stripped")
    logger.info(f"silver.employee: {per_diem:,} employees marked per diem")
    return loaded


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)s [%(filename)s:%(lineno)d] %(message)s",
    )
    run_id = manual_run_id()  # one ID for both tables in this run
    build_silver_timesheet(run_id)
    build_silver_employee(run_id)
