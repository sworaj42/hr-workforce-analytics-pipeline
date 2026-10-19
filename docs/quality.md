# Quality checks and report

The last two DAG tasks: `build_gold >> quality_checks >> generate_report`.

## Checks (`pipeline/quality.py`)

Each check is one SQL query. Results are saved to `gold.dq_results` (one row per
check per run).

| Check | Fails when |
|---|---|
| `fact_matches_silver` | the fact and silver timesheet row counts differ |
| `all_silver_employees_in_gold` | a silver employee is missing from `dim_employee` |
| `inferred_match_timesheets` | inferred employees differ from the timesheet IDs not in the employee file |
| `reject_rate_ok` | a silver table rejected more than `DQ_MAX_REJECT_PCT` % of its source rows (`.env`, default 1) |
| `no_negative_hours` | a fact row has `hours_worked` < 0 |
| `kpis_not_empty` | `kpi_active_headcount` or `kpi_avg_working_hours` returns no rows |

Duplicate punches and broken links to dates, employees or departments aren't
checked here: the primary key and foreign keys already make them impossible.

## On failure

- All results are saved first, then `quality_checks` fails at once
  (`AirflowFailException`, no retry: bad data won't fix itself). A database
  error still gets the normal retries.
- `generate_report` runs anyway (`trigger_rule="all_done"`) and the report
  shows which check failed. It then fails too, so the DAG run is marked failed
  rather than green.

## Report (`pipeline/report.py`)

One Markdown file per run in `reports/report_<run_id>.md` (gitignored; example:
`docs/sample_report.md`): the latest silver load per table, this run's check
results, and headline KPIs.

## Known limitation

`inferred_match_timesheets` would fail after a silver full reload if an
employee created through the API had punches: gold keeps that employee as a
real (deleted) row, not an inferred one. API-created employees have no punches
today.
