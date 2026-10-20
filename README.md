# HR Workforce Pipeline

An end-to-end ELT pipeline for hospital workforce data. Raw employee and timesheet extracts land in MinIO, are loaded and cleaned through bronze, silver, and gold layers in PostgreSQL under Airflow orchestration, and are served through a FastAPI service and a Streamlit dashboard. Everything runs in Docker.

![Pipeline architecture](docs/architecture.svg)

## Docs

- [Setup](docs/setup.md)
- [Schema](docs/schema.md)
- [Assumptions](docs/assumptions.md)
- [KPIs](docs/kpis.md)
- [Data quality](docs/quality.md) · [sample report](docs/sample_report.md)
- [API](docs/api.md)
- [Indexing](docs/indexing.md)
