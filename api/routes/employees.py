from fastapi import APIRouter, HTTPException
from psycopg2.extras import RealDictCursor

from api.schemas import EmployeeCreate, EmployeeUpdate
from pipeline.db import get_connection

router = APIRouter(prefix="/employees", tags=["employees"])

# Columns returned by every employee endpoint.
EMPLOYEE_COLUMNS = """
    client_employee_id, first_name, last_name, job_code, job_title,
    organization_name, department_id, department_name, fte_status,
    scheduled_weekly_hour, manager_employee_id, hire_date, recent_hire_date,
    term_date, active_status, termination_reason, is_per_diem, source_file
"""

# The only columns PATCH may set.
UPDATABLE_COLUMNS = set(EmployeeUpdate.model_fields)


@router.get("")
def list_employees(limit: int = 50, offset: int = 0):
    """List employees, a page at a time."""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                f"""
                SELECT {EMPLOYEE_COLUMNS}
                FROM silver.employee
                WHERE NOT is_deleted
                ORDER BY client_employee_id
                LIMIT %s OFFSET %s
                """,
                (limit, offset),
            )
            return cur.fetchall()
    finally:
        conn.close()


@router.get("/{employee_id}")
def get_employee(employee_id: str):
    """One employee by ID."""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                f"""
                SELECT {EMPLOYEE_COLUMNS}
                FROM silver.employee
                WHERE client_employee_id = %s AND NOT is_deleted
                """,
                (employee_id,),
            )
            row = cur.fetchone()
    finally:
        conn.close()

    if row is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    return row


@router.post("", status_code=201)
def create_employee(employee: EmployeeCreate):
    """Add an employee; the pipeline keeps API-owned rows (source_file = 'api')."""
    conn = get_connection()
    try:
        with conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Same per-diem rule as silver_employee.sql. DO NOTHING: an existing ID returns no row.
            cur.execute(
                f"""
                INSERT INTO silver.employee (
                    client_employee_id, first_name, last_name, job_code, job_title,
                    organization_name, department_id, department_name, fte_status,
                    scheduled_weekly_hour, manager_employee_id, hire_date, recent_hire_date,
                    active_status, is_per_diem, source_file
                )
                VALUES (
                    %(client_employee_id)s, %(first_name)s, %(last_name)s, %(job_code)s, %(job_title)s,
                    %(organization_name)s, %(department_id)s, %(department_name)s, %(fte_status)s,
                    %(scheduled_weekly_hour)s, %(manager_employee_id)s, %(hire_date)s, %(hire_date)s,
                    true, COALESCE(%(job_title)s LIKE '%%- PD', false), 'api'
                )
                ON CONFLICT (client_employee_id) DO NOTHING
                RETURNING {EMPLOYEE_COLUMNS}
                """,
                employee.model_dump(),
            )
            row = cur.fetchone()
    finally:
        conn.close()

    if row is None:
        raise HTTPException(status_code=409, detail="Employee ID already exists")
    return row


@router.patch("/{employee_id}")
def update_employee(employee_id: str, employee: EmployeeUpdate):
    """Change only the fields sent; source_file is never changed."""
    fields = employee.model_dump(exclude_unset=True)
    conn = get_connection()
    try:
        with conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT hire_date, term_date FROM silver.employee "
                "WHERE client_employee_id = %(employee_id)s AND NOT is_deleted FOR UPDATE",
                {"employee_id": employee_id},
            )
            current = cur.fetchone()
            if current is None:
                raise HTTPException(status_code=404, detail="Employee not found")

            hire_date = fields.get("hire_date", current["hire_date"])
            term_date = fields.get("term_date", current["term_date"])
            if hire_date and term_date and term_date < hire_date:
                raise HTTPException(status_code=400, detail="term_date is before hire_date")

            # Column names come from the allowed set, values go in as placeholders.
            set_list = [f"{col} = %({col})s" for col in fields if col in UPDATABLE_COLUMNS]
            if "job_title" in fields:
                # The new title, not the column: SET reads the old row.
                set_list.append("is_per_diem = COALESCE(%(job_title)s LIKE '%%- PD', false)")
            if "term_date" in fields:
                set_list.append("active_status = %(term_date)s::date IS NULL")
            set_list.append("loaded_at = now()")

            cur.execute(
                f"""
                UPDATE silver.employee
                SET {", ".join(set_list)}
                WHERE client_employee_id = %(employee_id)s
                RETURNING {EMPLOYEE_COLUMNS}
                """,
                {**fields, "employee_id": employee_id},
            )
            return cur.fetchone()
    finally:
        conn.close()


@router.delete("/{employee_id}", status_code=204)
def delete_employee(employee_id: str):
    """Soft delete: the row stays, flagged is_deleted."""
    conn = get_connection()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE silver.employee SET is_deleted = true, loaded_at = now() "
                "WHERE client_employee_id = %(employee_id)s AND NOT is_deleted",
                {"employee_id": employee_id},
            )
            deleted = cur.rowcount
    finally:
        conn.close()

    if deleted == 0:
        raise HTTPException(status_code=404, detail="Employee not found")
