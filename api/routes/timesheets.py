from datetime import date

from fastapi import APIRouter, HTTPException, Query
from psycopg2.extras import RealDictCursor

from pipeline.db import get_connection

router = APIRouter(tags=["timesheets"])


def fetch_timesheets(employee_id, start_date, end_date, limit, offset):
    """Timesheet entries from silver; each filter is skipped when it's None."""
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date is after end_date")

    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT client_employee_id, punch_apply_date, punch_in_datetime,
                       punch_out_datetime, hours_worked, pay_code, department_id,
                       department_name, scheduled_start_datetime, scheduled_end_datetime
                FROM silver.timesheet
                WHERE (%(employee_id)s::text IS NULL OR client_employee_id = %(employee_id)s)
                  AND (%(start_date)s::date IS NULL OR punch_apply_date >= %(start_date)s)
                  AND (%(end_date)s::date   IS NULL OR punch_apply_date <= %(end_date)s)
                ORDER BY punch_apply_date, client_employee_id, punch_in_datetime
                LIMIT %(limit)s OFFSET %(offset)s
                """,
                {
                    "employee_id": employee_id,
                    "start_date": start_date,
                    "end_date": end_date,
                    "limit": limit,
                    "offset": offset,
                },
            )
            return cur.fetchall()
    finally:
        conn.close()


@router.get("/employees/{employee_id}/timesheets")
def list_employee_timesheets(
    employee_id: str,
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """One employee's timesheet entries, a page at a time."""
    return fetch_timesheets(employee_id, start_date, end_date, limit, offset)


@router.get("/timesheets")
def list_timesheets(
    employee_id: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """All timesheet entries, optionally for one employee, a page at a time."""
    return fetch_timesheets(employee_id, start_date, end_date, limit, offset)
