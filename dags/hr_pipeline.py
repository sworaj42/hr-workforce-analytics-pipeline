"""
HR pipeline: land raw files in bronze, then build the cleaned silver layer.

The DAG only orchestrates; the logic lives in pipeline/ and can also be run
without Airflow (python -m pipeline.load_bronze / python -m pipeline.build_silver).
"""

from datetime import datetime, timedelta

from airflow.sdk import dag, task


@dag(
    schedule=None,  # manual trigger for now; scheduling is decided with the incremental load
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["bronze", "silver"],
    default_args={
        # Safe to retry: bronze reloads each file with delete-then-insert, and
        # silver is rebuilt with TRUNCATE + INSERT in one transaction, so a
        # rerun never duplicates rows.
        "retries": 2,
        "retry_delay": timedelta(minutes=1),
    },
)
def hr_pipeline():
    @task
    def load_bronze():
        # Imported inside the task so the DAG processor, which re-parses this
        # file every few seconds, does not import database/MinIO libraries.
        from pipeline.load_bronze import load_all_files

        load_all_files()

    @task
    def build_silver():
        from pipeline.build_silver import build_silver_timesheet

        build_silver_timesheet()

    # Silver reads from bronze, so it runs only after the bronze load succeeds.
    load_bronze() >> build_silver()


hr_pipeline()
