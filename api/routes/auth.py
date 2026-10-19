from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm

from api.auth import create_token, unauthorized, verify_password
from pipeline.db import get_connection

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/token")
def login(form: OAuth2PasswordRequestForm = Depends()):
    """Swap a username and password for a bearer token."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT password_hash, role FROM app.api_user WHERE username = %s",
                (form.username,),
            )
            row = cur.fetchone()
    finally:
        conn.close()

    # Same message for both cases, so the response doesn't reveal which usernames exist.
    if row is None or not verify_password(form.password, row[0]):
        raise unauthorized("Incorrect username or password")
    return {"access_token": create_token(form.username, row[1]), "token_type": "bearer"}
