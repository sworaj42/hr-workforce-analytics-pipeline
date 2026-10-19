from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field


class EmployeeCreate(BaseModel):
    client_employee_id: str = Field(min_length=1)
    first_name: str
    last_name: str | None = None
    job_code: str | None = None
    job_title: str | None = None
    organization_name: str | None = None
    department_id: str | None = None
    department_name: str | None = None
    fte_status: str | None = None
    scheduled_weekly_hour: Decimal | None = Field(None, ge=0, le=168)  # fits NUMERIC(5,2)
    manager_employee_id: str | None = None
    hire_date: date


class EmployeeUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    job_code: str | None = None
    job_title: str | None = None
    organization_name: str | None = None
    department_id: str | None = None
    department_name: str | None = None
    fte_status: str | None = None
    scheduled_weekly_hour: Decimal | None = Field(None, ge=0, le=168)
    manager_employee_id: str | None = None
    hire_date: date | None = None
    term_date: date | None = None
    termination_reason: str | None = None
