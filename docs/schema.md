# Schema

One Postgres database (`hr_warehouse`) with a schema per medallion layer:
`bronze` (raw), `silver` (clean), `gold` (star schema and KPI views). Every
table is created by the SQL files in `migrations/`.

## Gold: star schema

![Gold star schema](gold_schema.svg)

The diagram shows keys and the main columns; the full lists are below.
PK = primary key, FK = foreign key, UK = unique natural key. On the lines, the
fork means many, two bars mean exactly one, and the circle means zero or one.

### Relationships

| From `fact_timesheet` | To | Can be NULL |
|---|---|---|
| `employee_key` | `dim_employee` | no |
| `date_key` | `dim_date` | no |
| `department_key` | `dim_department` | yes, about 35% of punches have no department |
| `home_department_key` | `dim_department` | yes, about 31% have no home department |

A missing department stays NULL rather than pointing to an "Unknown" row; KPI
views show it as "No department".

### `gold.fact_timesheet`

One row per employee per punch-in. PK (`employee_key`, `punch_in_datetime`).

| Columns | Notes |
|---|---|
| `employee_key`, `date_key`, `department_key`, `home_department_key` | keys to the dimensions; `date_key` is the punch apply date as `YYYYMMDD` |
| `punch_in_datetime`, `punch_out_datetime`, `scheduled_start_datetime`, `scheduled_end_datetime`, `punch_apply_date` | local wall-clock time (`timestamp`, no time zone in the source) |
| `hours_worked` | `numeric(5,2)` |
| `pay_code`, `punch_in_comment`, `punch_out_comment` | as cleaned in silver |
| `has_schedule` | both scheduled times present |
| `is_incomplete` | no punch-out, or punch-out after the file was extracted |
| `is_worked` | false for time-off bookings (see `docs/assumptions.md`) |
| `client_employee_id` | natural employee ID, kept for readability |
| `source_file`, `source_row_num`, `loaded_at` | lineage back to bronze |

### `gold.dim_employee`

One row per employee. PK `employee_key`, UK `client_employee_id`.

- 50 rows come from the employee file. Every other employee seen in the
  timesheets gets an inferred row (`is_inferred = true`, details empty), so
  every fact row has an employee. A check enforces
  `is_inferred = (source_file IS NULL)`.
- `is_deleted` mirrors the API's soft delete in silver.
- Columns: `first_name`, `job_code`, `job_title`, `job_start_date`,
  `organization_name`, `department_id`, `department_name`, `fte_status`,
  `scheduled_weekly_hour`, `manager_employee_id`, `hire_date`,
  `recent_hire_date`, `term_date`, `active_status`, `termination_reason`,
  `is_per_diem`, plus lineage (`source_file`, `source_row_num`, `loaded_at`).

### `gold.dim_department`

One row per department ID. PK `department_key`, UK `department_id`.

- Built from every department ID in the timesheets (worked and home) and the
  employee file.
- `department_name` is the name from the latest file that gives one;
  `department_label` is `name (id)`, or just the ID when no name was ever given.

### `gold.dim_date`

One row per day, 1990 to 2025. PK `date_key` (`YYYYMMDD`), UK `full_date`.
Columns: `year`, `quarter`, `month`, `month_name`, `week_of_year`,
`day_of_week` (0 = Sunday), `day_name`, `is_weekend`. Checks keep `quarter`,
`month` and `day_of_week` in range.

### Also in gold

- `dq_results`: one row per quality check per run (`docs/quality.md`).
- `kpi_*` views: the KPIs, read from the four tables above (`docs/kpis.md`).

## Silver

| Table | Grain | Key |
|---|---|---|
| `silver.employee` | one row per employee | PK `client_employee_id` |
| `silver.timesheet` | one row per employee per punch-in | PK (`client_employee_id`, `punch_in_datetime`) |
| `silver.employee_rejects` | one row per rejected bronze row | none; values as in bronze plus `reject_reason` |
| `silver.timesheet_rejects` | one row per rejected bronze row | none; values as in bronze plus `reject_reason` |
| `silver.cleaning_log` | one row per silver table per build | none; a retried task adds a row |

There is no foreign key from `silver.timesheet` to `silver.employee`: the
timesheets name 10,773 employees and only 29 are in the employee file. Silver
keeps the source as delivered; gold makes it complete with inferred employees.

## Bronze

`bronze.employee_raw` and `bronze.timesheet_raw` hold every source column as
`TEXT`, exactly as in the file, plus `source_file`, `source_row_num` and
`loaded_at`. PK (`source_file`, `source_row_num`), so reloading a file replaces
its rows instead of duplicating them.

## Other tables

- `app.api_user`: API logins (PK `username`, `role` checked to be `admin` or
  `viewer`, bcrypt password hash).
- `public.schema_migrations`: migration files already applied.

Indexes beyond the keys are described in `docs/indexing.md`.
