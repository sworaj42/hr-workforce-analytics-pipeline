# HR Workforce Pipeline

End-to-end ELT pipeline for employee and timesheet data: MinIO → Postgres (bronze → silver → gold) → API and dashboard, orchestrated by Airflow.

![Pipeline architecture](docs/architecture.svg)

## Docs

- [Setup](docs/setup.md)
- [Assumptions](docs/assumptions.md)
- [KPIs](docs/kpis.md)
- [Data quality](docs/quality.md) · [sample report](docs/sample_report.md)
- [API](docs/api.md)
- [Indexing](docs/indexing.md)
