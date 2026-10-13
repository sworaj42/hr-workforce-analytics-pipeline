FROM apache/airflow:3.3.0

# Install our pipeline's libraries on top of the stock image. The constraints
# file pins every package Airflow itself depends on, so adding ours can never
# silently upgrade or downgrade something Airflow needs. The URL must match
# the base image's Airflow version (3.3.0) and Python version (3.13).
COPY requirements.txt /requirements.txt
RUN pip install --no-cache-dir -r /requirements.txt \
    --constraint https://raw.githubusercontent.com/apache/airflow/constraints-3.3.0/constraints-3.13.txt
