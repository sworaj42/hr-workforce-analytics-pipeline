"""
Data quality checks after each gold build (course Week6 quality.py pattern).

Each check is one SQL query that returns {check, passed, detail}. Only things the
schema can't guarantee are checked: duplicates and broken links are already
prevented by primary and foreign keys.

Run from the project root:  python -m pipeline.quality
"""

import logging
import os

from pipeline.build_silver import manual_run_id
from pipeline.db import get_connection

logger = logging.getLogger(__name__)

# Highest share of rejected source rows (percent) before the run fails.
MAX_REJECT_PCT = float(os.getenv("DQ_MAX_REJECT_PCT", "1"))


class DataQualityError(Exception):
    """One or more quality checks failed."""


def result(check: str, passed: bool, detail: str) -> dict:
    return {"check": check, "passed": passed, "detail": detail}


def fact_matches_silver(cur) -> dict:
    # Every silver punch should reach the fact (inferred employees make sure of it).
    cur.execute(
        "SELECT (SELECT count(*) FROM gold.fact_timesheet), (SELECT count(*) FROM silver.timesheet)"
    )
    fact, silver = cur.fetchone()
    return result("fact_matches_silver", fact == silver, f"fact {fact:,} vs silver {silver:,}")


def all_silver_employees_in_gold(cur) -> dict:
    cur.execute(
        """
        SELECT count(*) FROM silver.employee AS s
        WHERE NOT EXISTS (
            SELECT 1 FROM gold.dim_employee AS d WHERE d.client_employee_id = s.client_employee_id
        )
        """
    )
    missing = cur.fetchone()[0]
    return result("all_silver_employees_in_gold", missing == 0, f"{missing:,} missing from gold")


def inferred_match_timesheets(cur) -> dict:
    # Inferred employees = timesheet IDs that aren't in the employee file.
    cur.execute(
        """
        SELECT
            (SELECT count(*) FROM gold.dim_employee WHERE is_inferred),
            (SELECT count(DISTINCT t.client_employee_id) FROM silver.timesheet AS t
             WHERE NOT EXISTS (
                 SELECT 1 FROM silver.employee AS s WHERE s.client_employee_id = t.client_employee_id
             ))
        """
    )
    inferred, expected = cur.fetchone()
    return result(
        "inferred_match_timesheets", inferred == expected,
        f"{inferred:,} inferred vs {expected:,} timesheet-only IDs",
    )


def reject_rate_ok(cur) -> dict:
    # Latest cleaning_log row per silver table; a high share of rejects means a bad file.
    cur.execute(
        """
        SELECT DISTINCT ON (table_name)
            table_name, rows_rejected * 100.0 / NULLIF(rows_read, 0) AS reject_pct
        FROM silver.cleaning_log
        ORDER BY table_name, logged_at DESC
        """
    )
    rates = cur.fetchall()
    passed = len(rates) > 0 and all((pct or 0) <= MAX_REJECT_PCT for _, pct in rates)
    detail = ", ".join(f"{table} {pct or 0:.2f}%" for table, pct in rates) or "no cleaning_log rows"
    return result("reject_rate_ok", passed, f"{detail} (max {MAX_REJECT_PCT:g}%)")


def no_negative_hours(cur) -> dict:
    cur.execute("SELECT count(*) FROM gold.fact_timesheet WHERE hours_worked < 0")
    negative = cur.fetchone()[0]
    return result("no_negative_hours", negative == 0, f"{negative:,} rows with hours_worked < 0")


def kpis_not_empty(cur) -> dict:
    cur.execute(
        "SELECT (SELECT count(*) FROM gold.kpi_active_headcount), "
        "(SELECT count(*) FROM gold.kpi_avg_working_hours)"
    )
    headcount, hours = cur.fetchone()
    return result(
        "kpis_not_empty", headcount > 0 and hours > 0,
        f"kpi_active_headcount {headcount:,} rows, kpi_avg_working_hours {hours:,} rows",
    )


CHECKS = [
    fact_matches_silver,
    all_silver_employees_in_gold,
    inferred_match_timesheets,
    reject_rate_ok,
    no_negative_hours,
    kpis_not_empty,
]


def run_checks(cur) -> list[dict]:
    """Run every check on this cursor (also used to test checks inside a rolled-back transaction)."""
    return [check(cur) for check in CHECKS]


def run_quality_checks(run_id: str | None = None) -> list[dict]:
    """Run all checks, save every result, then raise if any failed."""
    run_id = run_id or manual_run_id()
    conn = get_connection()
    try:
        with conn, conn.cursor() as cur:
            results = run_checks(cur)
            for r in results:
                cur.execute(
                    "INSERT INTO gold.dq_results (run_id, check_name, passed, detail) "
                    "VALUES (%s, %s, %s, %s)",
                    (run_id, r["check"], r["passed"], r["detail"]),
                )
                log = logger.info if r["passed"] else logger.error
                log(f"{'PASS' if r['passed'] else 'FAIL'}  {r['check']}: {r['detail']}")
    finally:
        conn.close()

    # Raised after the commit above, so failed results are saved too.
    failed = [r["check"] for r in results if not r["passed"]]
    if failed:
        raise DataQualityError(f"{len(failed)} check(s) failed: {', '.join(failed)}")
    return results


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)s [%(filename)s:%(lineno)d] %(message)s",
    )
    run_quality_checks()
