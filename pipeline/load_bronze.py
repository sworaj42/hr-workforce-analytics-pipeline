"""
Land raw source files in the bronze layer, from the MinIO landing bucket
(source "minio", the default) or from a local folder (source "local").

Each file is streamed straight into Postgres. For each file: COPY it into a
temp table, delete any rows previously loaded
from the same file, and insert the new rows with lineage metadata
(source_file, source_row_num). All of that happens in one transaction per
file, so a rerun never duplicates rows and a failure leaves the previous load
untouched.

Run from the project root:  python -m pipeline.load_bronze [--source local]
In Airflow: dags/hr_pipeline.py calls load_all_files() with the run's source param.
"""

import argparse
import logging
import os
import re
import time
from pathlib import Path

from dotenv import load_dotenv
from minio import Minio

from pipeline.db import get_connection

logger = logging.getLogger(__name__)

load_dotenv()

BUCKET = os.getenv("MINIO_BUCKET")
LOCAL_DATA_DIR = os.getenv("LOCAL_DATA_DIR", "data")

# Source name -> bronze table it lands in
TARGET_TABLES = {
    "employee": "bronze.employee_raw",
    "timesheet": "bronze.timesheet_raw",
}
# e.g. timesheet_202509151540.csv (extraction time YYYYMMDDHHMM)
FILE_NAME = re.compile(rf"^({'|'.join(TARGET_TABLES)})_\d{{12}}\.csv$")


def get_minio_client() -> Minio:
    return Minio(
        os.getenv("MINIO_ENDPOINT"),
        access_key=os.getenv("MINIO_ROOT_USER"),
        secret_key=os.getenv("MINIO_ROOT_PASSWORD"),
        secure=False,  # local MinIO serves plain HTTP
    )


def target_table_for(file_name: str) -> str:
    match = FILE_NAME.match(file_name)
    if not match:
        raise ValueError(f"'{file_name}' does not match <table>_YYYYMMDDHHMM.csv")
    return TARGET_TABLES[match.group(1)]


def read_header(file_obj) -> list:
    """Column names from the first line, e.g. "a"|"b" -> ['a', 'b']."""
    header = file_obj.readline().decode("utf-8").strip()
    return [col.strip('"') for col in header.split("|")]


def table_source_columns(conn, table: str) -> list:
    """Columns of a bronze table, excluding the metadata columns we add."""
    schema, name = table.split(".")
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
              AND column_name NOT IN ('source_file', 'source_row_num', 'loaded_at')
            ORDER BY ordinal_position
            """,
            (schema, name),
        )
        return [row[0] for row in cur.fetchall()]


def load_file(conn, file_obj, file_name: str) -> int:
    """Load one file (a binary file-like object) into its bronze table.
    Returns the number of rows loaded."""
    table = target_table_for(file_name)
    columns = read_header(file_obj)

    # Fail loudly if the source layout changed, instead of loading shifted columns.
    # This also means only known column names ever reach the SQL below.
    expected = table_source_columns(conn, table)
    if columns != expected:
        raise ValueError(
            f"{file_name}: header does not match {table}. "
            f"Unexpected: {sorted(set(columns) - set(expected))}, "
            f"missing: {sorted(set(expected) - set(columns))}"
        )
    col_list = ", ".join(columns)

    try:
        with conn.cursor() as cur:
            # Temp table: same columns as the file, all TEXT, plus a counter that
            # numbers rows in the order COPY reads them (= order in the file).
            col_defs = ", ".join(f"{c} TEXT" for c in columns)
            cur.execute(f"""
                CREATE TEMP TABLE stage_raw (
                    row_num INTEGER GENERATED ALWAYS AS IDENTITY,
                    {col_defs}
                ) ON COMMIT DROP
            """)

            # Header line was already consumed by read_header(), so HEADER false.
            # CSV mode handles quoted values that contain '|' or line breaks.
            cur.copy_expert(
                f"COPY stage_raw ({col_list}) FROM STDIN "
                f"WITH (FORMAT csv, DELIMITER '|', QUOTE '\"', HEADER false, ENCODING 'UTF8')",
                file_obj,
            )

            cur.execute(f"DELETE FROM {table} WHERE source_file = %s", (file_name,))
            replaced = cur.rowcount

            cur.execute(
                f"""
                INSERT INTO {table} ({col_list}, source_file, source_row_num)
                SELECT {col_list}, %s, row_num FROM stage_raw
                """,
                (file_name,),
            )
            loaded = cur.rowcount
        conn.commit()
    except Exception:
        conn.rollback()
        logger.exception(f"Failed to load {file_name} into {table} — rolled back")
        raise

    logger.info(f"{file_name} -> {table}: {loaded:,} rows loaded ({replaced:,} previous rows replaced)")
    return loaded


def minio_files():
    """Yield (name, file object) for each CSV in the landing bucket, oldest first."""
    client = get_minio_client()
    names = sorted(
        obj.object_name
        for obj in client.list_objects(BUCKET)
        if obj.object_name.endswith(".csv")
    )
    for name in names:
        # get_object returns a streaming HTTP response; COPY reads from it
        # in chunks, so the file is never held in memory as a whole.
        response = client.get_object(BUCKET, name)
        try:
            yield name, response
        finally:
            response.close()
            response.release_conn()


def local_files():
    """Yield (name, file object) for each CSV in LOCAL_DATA_DIR, oldest first."""
    for path in sorted(Path(LOCAL_DATA_DIR).glob("*.csv")):
        with open(path, "rb") as file_obj:
            yield path.name, file_obj


def load_all_files(source="minio"):
    """Load every source CSV into bronze, one transaction per file."""
    if source == "minio":
        files, where = minio_files(), f"bucket '{BUCKET}'"
    elif source == "local":
        files, where = local_files(), f"folder '{LOCAL_DATA_DIR}'"
    else:
        raise ValueError(f"source must be 'minio' or 'local', got '{source}'")

    logger.info(f"Loading files from {where}")
    loaded = 0
    conn = get_connection()
    try:
        for name, file_obj in files:
            start = time.time()
            load_file(conn, file_obj, name)
            loaded += 1
            logger.info(f"  took {time.time() - start:.1f}s")
    finally:
        conn.close()
    if loaded == 0:
        raise FileNotFoundError(f"No CSV files found in {where}")
    logger.info(f"Bronze load finished: {loaded} file(s) from {where}")


def parse_args():
    parser = argparse.ArgumentParser(description="Load source files into bronze")
    parser.add_argument(
        "--source",
        choices=["minio", "local"],
        default="minio",
        help="Read files from the MinIO bucket (default) or from LOCAL_DATA_DIR",
    )
    return parser.parse_args()


if __name__ == "__main__":
    # Logging is configured only when run as a script; under Airflow the task
    # runner sets up logging and this module's logger feeds into it.
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)s [%(filename)s:%(lineno)d] %(message)s",
    )
    load_all_files(parse_args().source)
