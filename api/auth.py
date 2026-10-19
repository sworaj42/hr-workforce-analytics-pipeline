"""Password hashing, JWT tokens and the login dependencies for the API."""

import os
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from dotenv import load_dotenv
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer

load_dotenv()

# os.environ, not getenv: a missing secret stops the API at startup.
JWT_SECRET = os.environ["JWT_SECRET"]
JWT_EXPIRE_MINUTES = int(os.environ["JWT_EXPIRE_MINUTES"])

# Reads the "Authorization: Bearer <token>" header; 401 if it's missing.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:  # bcrypt rejects passwords over 72 bytes
        return False


def create_token(username: str, role: str) -> str:
    expires = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES)
    return jwt.encode({"sub": username, "role": role, "exp": expires}, JWT_SECRET, algorithm="HS256")


def unauthorized(detail: str) -> HTTPException:
    # The OAuth2 standard asks for this header on every 401.
    return HTTPException(status_code=401, detail=detail, headers={"WWW-Authenticate": "Bearer"})


def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    """The user from a valid token; the signature proves we issued it, so no DB lookup."""
    try:
        # Fixed algorithm list, so a token can't pick its own (e.g. "none"). Also checks exp.
        claims = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except jwt.InvalidTokenError:  # expired, tampered or malformed
        raise unauthorized("Invalid or expired token")
    return {"username": claims["sub"], "role": claims["role"]}


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    return user
