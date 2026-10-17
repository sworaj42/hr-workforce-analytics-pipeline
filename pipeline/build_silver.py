"""
Build the silver layer from bronze with set-based SQL inside Postgres.

The SQL lives in pipeline/sql/ (one rebuild script per silver table); this
module runs each script in its own transaction and logs row counts so every
run shows how many rows were rejected and how many duplicates were removed.

Run from the project root:  python -m pipeline.build_silver
"""

import logging
from pathlib import Path

from pipeline.db import get_connection

logger = logging.getLogger(__name__)

SQL_DIR = Path(__file__).parent / "sql"


def count_rows(cur, table: str) -> int:
    # Table names are fixed strings from this module, never user input.
    cur.execute(f"SELECT count(*) FROM {table}")
    return cur.fetchone()[0]


def rebuild_silver_table(sql_file: str, bronze_table: str, silver_table: str) -> int:
    """Run one rebuild script from pipeline/sql/. Returns the number of rows loaded."""
    sql = (SQL_DIR / sql_file).read_text(encoding="utf-8")
    conn = get_connection()
    try:
        # `with conn` commits on success and rolls back on any error, so
        # TRUNCATE + both INSERTs are applied together or not at all.
        with conn, conn.cursor() as cur:
            read = count_rows(cur, bronze_table)
            cur.execute(sql)
            # Counted, not rowcount: the script has several statements.
            rejected = count_rows(cur, f"{silver_table}_rejects")
            loaded = count_rows(cur, silver_table)
    finally:
        conn.close()

    logger.info(
        f"{silver_table}: {read:,} read | {rejected:,} rejected | "
        f"{read - rejected - loaded:,} duplicates removed | {loaded:,} loaded"
    )
    return loaded


def build_silver_timesheet() -> int:
    return rebuild_silver_table("silver_timesheet.sql", "bronze.timesheet_raw", "silver.timesheet")


def build_silver_employee() -> int:
    return rebuild_silver_table("silver_employee.sql", "bronze.employee_raw", "silver.employee")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)s [%(filename)s:%(lineno)d] %(message)s",
    )
    build_silver_timesheet()
    build_silver_employee()
