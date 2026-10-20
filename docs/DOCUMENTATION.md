# HR Workforce Analytics Pipeline: Project Documentation

**Assignment:** ETL to Insights (Associate Data Engineer)
**Candidate:** Swaraj Sigdel
**Repository:** https://github.com/sworaj42/hr-workforce-analytics-pipeline

This document covers the four required parts: engineering decisions, setup
instructions, the usage guide, and schema documentation. The project
overview, features, KPI definitions, data findings and assumptions are in the
repository.

---

## 1. Engineering decisions

### Technology choices

| Area | Choice | Why |
|---|---|---|
| Warehouse | PostgreSQL | Widely used, and I've worked with it in previous projects. Window functions, `DISTINCT ON`, fast `COPY` loading and constraints covered everything this pipeline needed. |
| Orchestration | Apache Airflow | I learned it in my data engineering bootcamp and have used it since. It handles task order, retries, run options and run history. |
| Transformations | SQL inside PostgreSQL | The data never leaves the database: nothing is copied into Python and written back, so it's faster and avoids extra work. |
| Database access | psycopg2 with plain SQL | Familiar from the bootcamp and previous projects, and every query stays visible and easy to explain. |
| Dashboard | Streamlit with Plotly | I've used Streamlit before, and it runs in Docker with the rest of the stack. Power BI wasn't an option on macOS. Plotly adds interactive charts. |
| Packaging | Docker Compose | The whole stack starts with one command and the same versions on any machine, so it can be run without installing anything else. |

### Architecture

![Architecture](docs/architecture.svg)

**Medallion architecture (ELT).** The files are loaded into PostgreSQL as
they are, then refined in three layers. Keeping the raw data meant I could
change a cleaning rule and rebuild silver and gold without reloading the
files, which happened several times as I learned more about the data. It also
keeps the two consumers apart: the API works on clean operational data in
silver, and the dashboard reads analysis-ready data in gold.

| Layer | What was done |
|---|---|
| Bronze | Files copied in unchanged, all columns as text, with the source file and row number |
| Silver | Values cleaned, validated and typed; failed rows kept in rejects tables; duplicates removed; flags derived |
| Gold | Star schema with surrogate keys, inferred employees, and KPI views |

### Loading

**Idempotent loads.** Every step can be rerun without duplicating data. The
method depends on the table:

| Table | Method | Matched on |
|---|---|---|
| Bronze tables | Delete the file's earlier rows, then insert the file again, in one transaction | `source_file` |
| `silver.timesheet`, `gold.fact_timesheet` | Delete the window (30 days back from the latest date already loaded), then insert it again from the layer below, in one transaction; older rows are left untouched | `punch_apply_date` |
| `silver.employee` | Upsert; a row is overwritten only when a different file supplies it, and a delete is never undone | `client_employee_id` |
| `dim_employee`, `dim_department` | Upsert on the source ID, so surrogate keys stay stable and the fact's foreign keys never break; inferred employees are added only if missing | `client_employee_id`, `department_id` |
| `dim_date` | Insert missing days only; existing dates never change | `date_key` |

Each delete and insert runs in one transaction, so a failed step keeps the old
rows and retries are safe. Rerunning the same employee file changes nothing,
so API edits survive. Full and incremental runs give identical tables.

**Incremental loading.** Silver and gold load incrementally by default, using
the same pattern:

1. **Watermark:** find the latest `punch_apply_date` already in the table.
2. **Window start:** go back `INCREMENTAL_WINDOW_DAYS` (30) from it.
3. **Reload:** delete everything from the window start onward and insert it
   again from the layer below, in one transaction.

```sql
SELECT COALESCE(MAX(punch_apply_date) - 30, DATE '2000-01-01')
FROM silver.timesheet;
```

On an empty table the window falls back to 2000, so the first run loads
everything. `full_reload = true` truncates and reloads without a window.

**Deduplication.** The timesheet extracts overlap (22–26 Sep and 4–6 Oct), so
30,839 punches appear in two files. Silver keeps one row per employee and
punch-in time, taking the copy from the newest file:

```sql
SELECT DISTINCT ON (client_employee_id, punch_in_datetime) *
...
ORDER BY client_employee_id, punch_in_datetime, source_file DESC;
```

File names carry the extract timestamp, so sorting them descending puts the
newest file first. Dropped copies are counted in the cleaning log.

### Data quality and modeling

**Rejects.** Rows failing a validation rule go to `silver.timesheet_rejects`
or `silver.employee_rejects` instead of silver:

| Column | Content |
|---|---|
| source columns | values as in bronze (`TEXT`) |
| `reject_reason` | first rule failed (missing key, invalid date/number, punch-out before punch-in, …) |
| `source_file`, `source_row_num` | origin |
| `rejected_at` | time rejected |

**Cleaning log.** Each silver build adds one row per table to
`silver.cleaning_log`, committed with the data:

| Column | Content |
|---|---|
| `run_id`, `table_name`, `load_mode` | run, table, `incremental` or `full` |
| `window_start` | first date reloaded; empty for a full load |
| `rows_read` | rows in bronze |
| `rows_rejected` | sent to rejects |
| `rows_outside_window` | before the window, untouched |
| `rows_duplicate` | dropped by deduplication |
| `rows_loaded` | in silver from this build |
| `logged_at` | time logged |

**Quality checks.** After every gold build, six checks run on the finished
data, and each result is stored in `gold.dq_results`:

| Check | Fails when |
|---|---|
| Fact matches silver | `gold.fact_timesheet` and `silver.timesheet` have different row counts |
| Employees in gold | a silver employee is missing from `dim_employee` |
| Inferred employees match | the number of inferred employees differs from the number of timesheet IDs not in the employee file |
| Reject rate | either silver table's latest build rejects more than `DQ_MAX_REJECT_PCT` (1%) of rows read |
| No negative hours | any punch has `hours_worked` below 0 |
| KPIs not empty | the headcount or working-hours KPI views return no rows |

Duplicates and broken links aren't checked here, since the primary and
foreign keys already prevent them. A failed check fails the run without
retrying, and the run's Markdown report is still written to `reports/`.

- **Layout check.** Each file's header is compared with the bronze table
  before loading, so a changed layout fails instead of loading shifted columns.
- **Lineage.** Timesheet and employee rows in silver and gold, and rejected
  rows, keep `source_file` and `source_row_num`, the file and line they came
  from.
- **Inferred employees.** Timesheets name 10,773 employees, the employee file
  50. Each missing employee gets a placeholder row in gold, so every punch has
  a valid foreign key. HR KPIs use real employees only.
- **Worked time.** Bookings at exactly 00:00 under non-shift pay codes are
  time off, not clocked work (45,551 rows). They stay in the fact but are
  excluded from hours and attendance KPIs.
- **KPIs as views.** Always in step with the tables; computed in
  milliseconds at this size.

### Reliability and performance

- **Failure handling.** Tasks retry twice; every step replaces its data, so
  retries are safe.
- **Indexing.** Primary keys already cover employee lookups. Indexes on
  `punch_apply_date` in silver and the fact cut the API's one-week query from
  27.7 ms to 2.8 ms (381,732 → 4,977 rows read), measured with
  `EXPLAIN ANALYZE`.
- **Migrations.** Timestamped SQL files, applied automatically on start and
  recorded in `public.schema_migrations`.

### API

- Reads and writes silver, the clean operational layer; the dashboard reads
  gold.

| Silver table | Operations | Minimum role |
|---|---|---|
| `silver.employee` | list, get by ID (deleted rows hidden) | `viewer` |
| | create, update (fields sent only), soft delete | `admin` |
| `silver.timesheet` | read only: list all or one employee's, filter by date range, paginated | `viewer` |

- API-created employees and edits survive normal pipeline runs; a full reload
  resets employees to the source file.
- Deletes are soft: the row is flagged, so past timesheets still link to a
  valid employee, and deleted employees leave the HR KPIs.
- Every route needs a JWT token from `/auth/token`; passwords are stored as
  bcrypt hashes.

### Trade-offs

| Decision | Cost |
|---|---|
| 30-day incremental window | Older corrections need a full reload |
| Full reload resets employees | API changes are lost on a full reload |
| Soft deletes | Deleted employees stay in the database, so every query must filter `is_deleted` |
| Newest file wins in deduplication | If two versions of a punch differed, the older one would be replaced silently (only counted) |
| Inferred employees | Placeholder rows have no attributes (no department, hire date), so they appear in timesheet KPIs but not HR KPIs |
| `is_worked` derived from punch times and pay codes | An inference, not a source field, so some punches may be misclassified as worked or time off |
| `is_per_diem` derived from job titles ending in `- PD` | An assumed naming convention; a per-diem employee with a different title would be missed |
| Same department name under different IDs kept separate | Reports can show one department split across two rows (e.g. Emergency Unit) |

---

## 2. Setup instructions

**Requirements:** Docker Desktop (4 GB memory, about 6 GB disk). Free ports:
5433, 8000, 8080, 8501, 9000, 9001.

1. Clone the repository:
   ```
   git clone https://github.com/sworaj42/hr-workforce-analytics-pipeline.git
   cd hr-workforce-analytics-pipeline
   ```
2. Create the settings file. `.env.example` works unchanged for local use:
   ```
   cp .env.example .env
   ```
3. Start the stack. The first start builds images (several minutes);
   migrations and the MinIO upload run automatically:
   ```
   docker compose up -d
   ```
4. Check that everything is up: `migrations`, `minio-init` and
   `airflow-init` exit with code 0, the other services are running:
   ```
   docker compose ps -a
   ```
5. Open the services (the dashboard shows data after the first pipeline run;
   see the usage guide):

| Service | URL | Login (from `.env`) |
|---|---|---|
| Airflow | http://localhost:8080 | `AIRFLOW_ADMIN_USER` / `AIRFLOW_ADMIN_PASSWORD` |
| API docs | http://localhost:8000/docs | `admin` or `viewer` / `API_ADMIN_PASSWORD`, `API_VIEWER_PASSWORD` |
| Dashboard | http://localhost:8501 | none |
| MinIO console | http://localhost:9001 | `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` |

Verified from a fresh clone with `.env.example` unchanged. Full settings and
troubleshooting: `docs/setup.md`.

---

## 3. Usage guide

**Run the pipeline:** trigger `hr_pipeline` in Airflow, or:

```
docker compose exec airflow-scheduler airflow dags trigger hr_pipeline
```

| Option | Default | Effect |
|---|---|---|
| `full_reload` | `false` | `true` rebuilds silver and gold from scratch and resets employees to the source file |
| `source` | `minio` | `local` reads from `data/` |

In the UI, the Trigger dialog shows both options. From the command line:

```
docker compose exec airflow-scheduler \
  airflow dags trigger hr_pipeline \
  --conf '{"source": "local", "full_reload": true}'
```

**Reports:** each run writes `reports/report_<run_id>.md` with load counts,
quality results and headline KPIs (example: `docs/sample_report.md`).

**API:** log in at `/auth/token`, then send the token as a bearer header.
Without a token: 401; a write as `viewer`: 403. Examples in `docs/api.md`.
Tests: `python -m pytest`.

**Dashboard:** three tabs (Workforce, Working hours, Attendance); refresh
after a pipeline run.

**Stop:** `docker compose down` keeps the data; `down -v` deletes it.

---

## 4. Schema documentation

![Gold star schema](docs/gold_schema.svg)

| Table | Grain | Keys |
|---|---|---|
| `gold.fact_timesheet` | one per punch | PK (`employee_key`, `punch_in_datetime`) |
| `gold.dim_employee` | one per employee (50 real + 10,744 inferred) | PK `employee_key`, UK `client_employee_id` |
| `gold.dim_department` | one per department ID | PK `department_key`, UK `department_id` |
| `gold.dim_date` | one per day | PK `date_key` (`YYYYMMDD`) |

The fact links to employee and date (required) and to department twice,
worked and home, both nullable since about a third of punches have no
department.

**Silver** (cleaned and typed; no foreign keys between tables):

| Table | Grain | Key | Main columns |
|---|---|---|---|
| `silver.employee` | one per employee | PK `client_employee_id` | name, job code and title, organization, department, manager, FTE status, weekly hours, hire / recent hire / term dates, active status, termination reason, `is_per_diem`, `is_deleted` |
| `silver.timesheet` | one per punch | PK (`client_employee_id`, `punch_in_datetime`) | punch apply date, punch in / out, scheduled start / end, hours worked, pay code, department and home department, punch comments, `extracted_at`, `has_schedule`, `is_incomplete` |
| `silver.*_rejects` | one per rejected row | none | source values as text, `reject_reason` |
| `silver.cleaning_log` | one per table per run | none | row counts per run |

The employee, timesheet and rejects tables also keep `source_file` and
`source_row_num`.

**Bronze:** `employee_raw` and `timesheet_raw`, every source column as `TEXT`
plus `source_file`, `source_row_num` and `loaded_at`.
