"""
Apply the SQL migrations in migrations/ that haven't run yet (course Week2
pattern, plus a table recording which files are applied).

Files run in filename order, each in its own transaction together with its
record in public.schema_migrations, and the run stops at the first failure.

Run from the project root:  python -m pipeline.migrate
"""

import logging
import sys
from pathlib import Path

from pipeline.db import get_connection

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent.parent / "migrations"


def run_migrations(conn):
    with conn, conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS public.schema_migrations (
                filename    TEXT         PRIMARY KEY,
                applied_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
            )
            """
        )
        cur.execute("SELECT filename FROM public.schema_migrations")
        applied = {row[0] for row in cur.fetchall()}

    applied_now = 0
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        if path.name in applied:
            logger.info(f"skipped  {path.name}")
            continue
        # One transaction: the file and its record are committed together, or neither is.
        with conn, conn.cursor() as cur:
            cur.execute(path.read_text(encoding="utf-8"))  # no params, so % in the SQL is safe
            cur.execute("INSERT INTO public.schema_migrations (filename) VALUES (%s)", (path.name,))
        logger.info(f"applied  {path.name}")
        applied_now += 1

    logger.info(f"{applied_now} applied, {len(applied)} already applied")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)s [%(filename)s:%(lineno)d] %(message)s",
    )
    conn = get_connection()
    try:
        run_migrations(conn)
    except Exception:
        # Non-zero exit, so services waiting on this one don't start.
        logger.exception("Migration failed")
        sys.exit(1)
    finally:
        conn.close()
