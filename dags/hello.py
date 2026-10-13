"""
Smoke test: proves the scheduler can parse a DAG from dags/ and run a task.
"""

import logging
from datetime import datetime

from airflow.sdk import dag, task

logger = logging.getLogger(__name__)


@dag(
    schedule=None,  # manual trigger only
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["smoke-test"],
)
def hello():
    @task
    def say_hello():
        logger.info("Hello from Airflow")

    say_hello()


hello()
