# Small image for the HR API; the code is mounted by docker-compose.yml.
# Python 3.13 matches the Airflow image, so the pinned requirements work in both.
FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt /requirements.txt
RUN pip install --no-cache-dir -r /requirements.txt

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
