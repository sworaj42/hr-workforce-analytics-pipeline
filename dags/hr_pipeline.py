"""HR pipeline: bronze -> silver -> gold (logic lives in pipeline/)."""

from datetime import datetime, timedelta

from airflow.sdk import Param, dag, task


@dag(
    schedule=None,  # manual trigger for now
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,  # runs rebuild shared tables, so they must not overlap
    is_paused_upon_creation=False,  # ready after a fresh start; schedule=None keeps it manual
    tags=["bronze", "silver", "gold"],
    params={
        "full_reload": Param(
            False,
            type="boolean",
            description="Truncate-reload the timesheet tables instead of the default incremental load",
        ),
        "source": Param(
            "minio",
            enum=["minio", "local"],
            description="Where bronze reads the source files from: the MinIO bucket or the mounted data/ folder",
        ),
    },
    default_args={
        # Safe to retry: every step replaces its data, so a rerun never duplicates rows.
        "retries": 2,
        "retry_delay": timedelta(minutes=1),
    },
)
def hr_pipeline():
    @task
    def load_bronze(**context):
        # Imported here so DAG parsing stays light.
        from pipeline.load_bronze import load_all_files

        load_all_files(context["params"]["source"])

    # Module import because the task and the function share a name.
    @task
    def build_silver_timesheet(**context):
        from pipeline import build_silver

        build_silver.build_silver_timesheet(context["run_id"], context["params"]["full_reload"])

    @task
    def build_silver_employee(**context):
        from pipeline import build_silver

        build_silver.build_silver_employee(context["run_id"], context["params"]["full_reload"])

    @task
    def build_gold(**context):
        from pipeline import build_gold

        build_gold.build_gold(context["params"]["full_reload"])

    @task
    def quality_checks(**context):
        from airflow.exceptions import AirflowFailException

        from pipeline.quality import DataQualityError, run_quality_checks

        try:
            run_quality_checks(context["run_id"])
        except DataQualityError as e:
            # Bad data won't fix itself on a retry, so fail now (course pattern).
            raise AirflowFailException(str(e))

    # all_done: write a report even when an earlier task failed.
    @task(trigger_rule="all_done")
    def generate_report(**context):
        from airflow.exceptions import AirflowFailException

        from pipeline import report

        path, all_passed = report.generate_report(context["run_id"])
        # This is the last task, so it decides the run's colour: fail if checks failed or didn't run.
        if not all_passed:
            raise AirflowFailException(f"Quality checks failed or didn't run, see {path.name}")

    # Both silver tables read only from bronze, so they run in parallel; gold needs both.
    (
        load_bronze()
        >> [build_silver_timesheet(), build_silver_employee()]
        >> build_gold()
        >> quality_checks()
        >> generate_report()
    )


hr_pipeline()
