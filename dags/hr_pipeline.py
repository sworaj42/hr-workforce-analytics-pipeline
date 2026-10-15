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

    # The module is imported rather than the function, because the task and
    # the pipeline function share a name.
    @task
    def build_silver_timesheet():
        from pipeline import build_silver

        build_silver.build_silver_timesheet()

    @task
    def build_silver_employee():
        from pipeline import build_silver

        build_silver.build_silver_employee()

    # Both silver tables read only from bronze and not from each other, so
    # they wait for the bronze load and then run in parallel.
    load_bronze() >> [build_silver_timesheet(), build_silver_employee()]


hr_pipeline()
