"""
Bronze layer: land every raw file from the MinIO landing bucket in Postgres.

The DAG only orchestrates; the loading logic lives in pipeline/load_bronze.py
and can be run without Airflow (python pipeline/load_bronze.py).
"""

from datetime import datetime, timedelta

from airflow.sdk import dag, task


@dag(
    schedule=None,  # manual trigger for now; scheduling is decided with the incremental load
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["bronze"],
    default_args={
        # Safe to retry: each file is reloaded with delete-then-insert in one
        # transaction, so a rerun never duplicates rows.
        "retries": 2,
        "retry_delay": timedelta(minutes=1),
    },
)
def bronze():
    @task
    def load_bronze():
        # Imported inside the task so the DAG processor, which re-parses this
        # file every few seconds, does not import database/MinIO libraries.
        from pipeline.load_bronze import load_all_files

        load_all_files()

    load_bronze()


bronze()
