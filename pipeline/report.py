"""
Write a short Markdown report for a pipeline run: load summary, quality checks
and headline KPIs. Saved to reports/report_<run_id>.md.

Run from the project root:  python -m pipeline.report <run_id>
"""

import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from pipeline.db import get_connection

logger = logging.getLogger(__name__)

# <project root>/reports; mounted to the host folder in Docker.
REPORTS_DIR = Path(__file__).parent.parent / "reports"


def load_summary(cur) -> list[str]:
    cur.execute(
        """
        SELECT DISTINCT ON (table_name)
            table_name, load_mode, window_start, rows_read, rows_rejected,
            rows_outside_window, rows_duplicate, rows_loaded
        FROM silver.cleaning_log
        ORDER BY table_name, logged_at DESC
        """
    )
    lines = [
        "| Table | Mode | Window start | Read | Rejected | Outside window | Duplicates | Loaded |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for table, mode, window, read, rejected, outside, dup, loaded in cur.fetchall():
        lines.append(
            f"| {table} | {mode} | {window or '-'} | {read:,} | {rejected:,} "
            f"| {outside:,} | {dup:,} | {loaded:,} |"
        )
    return lines


def quality_section(cur, run_id: str) -> tuple[list[str], bool]:
    """The run's check results, and whether they all passed (False if none ran)."""
    cur.execute(
        "SELECT check_name, passed, detail FROM gold.dq_results WHERE run_id = %s ORDER BY check_name",
        (run_id,),
    )
    rows = cur.fetchall()
    if not rows:
        return ["Quality checks did not run for this run (an earlier task failed)."], False

    failed = sum(1 for _, passed, _ in rows if not passed)
    lines = [
        f"{len(rows) - failed} passed, {failed} failed.",
        "",
        "| Check | Result | Detail |",
        "|---|---|---|",
    ]
    for name, passed, detail in rows:
        lines.append(f"| {name} | {'PASS' if passed else '**FAIL**'} | {detail} |")
    return lines, failed == 0


def kpi_section(cur) -> list[str]:
    cur.execute(
        "SELECT as_of_date, active_count FROM gold.kpi_active_headcount "
        "ORDER BY as_of_date DESC LIMIT 1"
    )
    last_date, headcount = cur.fetchone() or (None, None)
    cur.execute("SELECT SUM(terminations) FROM gold.kpi_turnover_trend")
    terminations = cur.fetchone()[0]
    # Weighted by days worked, so it's the average over all employee-days.
    cur.execute(
        "SELECT SUM(avg_daily_hours * days_worked) / NULLIF(SUM(days_worked), 0) "
        "FROM gold.kpi_avg_working_hours"
    )
    avg_hours = cur.fetchone()[0]
    return [
        f"- Active headcount on {last_date}: {headcount}",
        f"- Terminations in the turnover period: {terminations}",
        f"- Average worked hours per employee per day: {avg_hours:.2f}" if avg_hours else
        "- Average worked hours per employee per day: no data",
    ]


def generate_report(run_id: str) -> tuple[Path, bool]:
    """Write the report; returns its path and whether this run's checks all passed."""
    conn = get_connection()
    try:
        with conn, conn.cursor() as cur:
            quality_lines, all_passed = quality_section(cur, run_id)
            lines = [
                "# Pipeline report",
                "",
                f"Run: `{run_id}`  ",
                f"Generated: {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC",
                "",
                "## Load summary (latest silver load per table)",
                "",
                *load_summary(cur),
                "",
                "## Quality checks",
                "",
                *quality_lines,
                "",
                "## Headline KPIs",
                "",
                *kpi_section(cur),
                "",
            ]
    finally:
        conn.close()

    # run_ids contain ':' and '+', which aren't safe in file names.
    safe_run_id = re.sub(r"[^A-Za-z0-9_-]", "_", run_id)
    REPORTS_DIR.mkdir(exist_ok=True)
    path = REPORTS_DIR / f"report_{safe_run_id}.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    logger.info(f"Report written to {path}")
    return path, all_passed


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)s [%(filename)s:%(lineno)d] %(message)s",
    )
    generate_report(sys.argv[1])
