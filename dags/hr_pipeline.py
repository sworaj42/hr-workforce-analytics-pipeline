"""HR pipeline: load raw files into bronze, then build silver (logic lives in pipeline/)."""

from datetime import datetime, timedelta

from airflow.sdk import dag, task


@dag(
    schedule=None,  # manual trigger for now
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,  # runs rebuild shared tables, so they must not overlap
    tags=["bronze", "silver"],
    default_args={
        # Safe to retry: every step replaces its data, so a rerun never duplicates rows.
        "retries": 2,
        "retry_delay": timedelta(minutes=1),
    },
)
def hr_pipeline():
    @task
    def load_bronze():
        # Imported here so DAG parsing stays light.
        from pipeline.load_bronze import load_all_files

        load_all_files()

    # Module import because the task and the function share a name; Airflow fills in run_id.
    @task
    def build_silver_timesheet(run_id=None):
        from pipeline import build_silver

        build_silver.build_silver_timesheet(run_id)

    @task
    def build_silver_employee(run_id=None):
        from pipeline import build_silver

        build_silver.build_silver_employee(run_id)

    # Both silver tables read only from bronze, so they run in parallel.
    load_bronze() >> [build_silver_timesheet(), build_silver_employee()]


hr_pipeline()
