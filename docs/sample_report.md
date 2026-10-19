# Pipeline report

Run: `manual__2026-10-19T08:54:36.539500+00:00`  
Generated: 2026-10-19 08:55 UTC

## Load summary (latest silver load per table)

| Table | Mode | Window start | Read | Rejected | Outside window | Duplicates | Loaded |
|---|---|---|---|---|---|---|---|
| silver.employee | incremental | - | 50 | 0 | 0 | 0 | 50 |
| silver.timesheet | incremental | 2025-09-16 | 412,571 | 0 | 269,921 | 30,839 | 111,811 |

## Quality checks

6 passed, 0 failed.

| Check | Result | Detail |
|---|---|---|
| all_silver_employees_in_gold | PASS | 0 missing from gold |
| fact_matches_silver | PASS | fact 381,732 vs silver 381,732 |
| inferred_match_timesheets | PASS | 10,744 inferred vs 10,744 timesheet-only IDs |
| kpis_not_empty | PASS | kpi_active_headcount 13,073 rows, kpi_avg_working_hours 9,622 rows |
| no_negative_hours | PASS | 0 rows with hours_worked < 0 |
| reject_rate_ok | PASS | silver.employee 0.00%, silver.timesheet 0.00% (max 1%) |

## Headline KPIs

- Active headcount on 2025-10-16: 44
- Terminations in the turnover period: 6
- Average worked hours per employee per day: 9.55
