"""
Build the silver layer from bronze with set-based SQL inside Postgres.

The SQL lives in pipeline/sql/; this module runs it in one transaction and
logs row counts so every run shows how many duplicates were removed.

Run from the project root:  python -m pipeline.build_silver
"""

import logging
from pathlib import Path

from pipeline.db import get_connection

logger = logging.getLogger(__name__)

SQL_DIR = Path(__file__).parent / "sql"


def build_silver_timesheet() -> int:
    """Rebuild silver.timesheet from bronze. Returns the number of rows written."""
    sql = (SQL_DIR / "silver_timesheet.sql").read_text(encoding="utf-8")
    conn = get_connection()
    try:
        # `with conn` commits on success and rolls back on any error, so
        # TRUNCATE + INSERT are applied together or not at all.
        with conn, conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM bronze.timesheet_raw")
            bronze_rows = cur.fetchone()[0]
            cur.execute(sql)
            silver_rows = cur.rowcount  # rows from the last statement, the INSERT
    finally:
        conn.close()

    logger.info(
        f"silver.timesheet: {silver_rows:,} rows from {bronze_rows:,} bronze rows "
        f"({bronze_rows - silver_rows:,} duplicates removed)"
    )
    return silver_rows


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)s [%(filename)s:%(lineno)d] %(message)s",
    )
    build_silver_timesheet()
