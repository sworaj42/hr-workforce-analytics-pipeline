"""
Create or update the API users, with passwords from .env. Safe to rerun.

Run from the project root:  python -m api.seed_users
"""

import logging
import os

from api.auth import hash_password
from pipeline.db import get_connection

logger = logging.getLogger(__name__)

# username -> env var with its password; the username is also the role.
USERS = {"admin": "API_ADMIN_PASSWORD", "viewer": "API_VIEWER_PASSWORD"}


def seed_users():
    conn = get_connection()
    try:
        with conn, conn.cursor() as cur:
            for username, password_var in USERS.items():
                cur.execute(
                    """
                    INSERT INTO app.api_user (username, password_hash, role)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (username) DO UPDATE SET
                        password_hash = EXCLUDED.password_hash,
                        role          = EXCLUDED.role
                    """,
                    (username, hash_password(os.environ[password_var]), username),
                )
                logger.info(f"User '{username}' created or updated")
    finally:
        conn.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)s %(message)s")
    seed_users()
