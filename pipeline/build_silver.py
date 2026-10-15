"""
Build the silver layer from bronze with set-based SQL inside Postgres.

The SQL lives in pipeline/sql/ (one rebuild script per silver table); this
module runs each script in its own transaction and logs row counts so every
run shows how many duplicates were removed.

Run from the project root:  python -m pipeline.build_silver
"""

import logging
from pathlib import Path

from pipeline.db import get_connection

logger = logging.getLogger(__name__)

SQL_DIR = Path(__file__).parent / "sql"


def rebuild_silver_table(sql_file: str, bronze_table: str, silver_table: str) -> int:
    """Run one rebuild script from pipeline/sql/. Returns the number of rows written."""
    sql = (SQL_DIR / sql_file).read_text(encoding="utf-8")
    conn = get_connection()
    try:
        # `with conn` commits on success and rolls back on any error, so
        # TRUNCATE + INSERT are applied together or not at all.
        with conn, conn.cursor() as cur:
            # Table names are fixed strings from this module, never user input.
            cur.execute(f"SELECT count(*) FROM {bronze_table}")
            bronze_rows = cur.fetchone()[0]
            cur.execute(sql)
            silver_rows = cur.rowcount  # rows from the last statement, the INSERT
    finally:
        conn.close()

    logger.info(
        f"{silver_table}: {silver_rows:,} rows from {bronze_rows:,} bronze rows "
        f"({bronze_rows - silver_rows:,} duplicates removed)"
    )
    return silver_rows


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
