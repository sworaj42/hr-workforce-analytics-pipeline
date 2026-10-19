"""
API tests against the real warehouse database; the users must be seeded (docs/api.md).

Run from the project root:  python -m pytest
"""

import os

from fastapi.testclient import TestClient

from api.main import app
from pipeline.db import get_connection

client = TestClient(app)

TEST_ID = "PYTEST001"
NEW_EMPLOYEE = {"client_employee_id": TEST_ID, "first_name": "Test", "hire_date": "2024-01-15"}


def login(username: str, password_var: str) -> dict:
    """Log in and return the Authorization header."""
    response = client.post(
        "/auth/token", data={"username": username, "password": os.environ[password_var]}
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_no_token_is_401():
    assert client.get("/employees").status_code == 401
    assert client.get("/timesheets").status_code == 401


def test_viewer_cannot_write():
    headers = login("viewer", "API_VIEWER_PASSWORD")
    assert client.post("/employees", json=NEW_EMPLOYEE, headers=headers).status_code == 403
    assert client.delete("/employees/00037", headers=headers).status_code == 403


def test_admin_create_read_delete():
    headers = login("admin", "API_ADMIN_PASSWORD")
    try:
        created = client.post("/employees", json=NEW_EMPLOYEE, headers=headers)
        assert created.status_code == 201
        assert created.json()["source_file"] == "api"

        assert client.get(f"/employees/{TEST_ID}", headers=headers).status_code == 200
        assert client.delete(f"/employees/{TEST_ID}", headers=headers).status_code == 204
        assert client.get(f"/employees/{TEST_ID}", headers=headers).status_code == 404
    finally:
        # Soft delete keeps the row; remove it so the test can run again.
        conn = get_connection()
        try:
            with conn, conn.cursor() as cur:
                cur.execute("DELETE FROM silver.employee WHERE client_employee_id = %s", (TEST_ID,))
        finally:
            conn.close()
