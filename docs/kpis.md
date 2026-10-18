# KPIs

KPI views live in the `gold` schema, created by
`migrations/20261018120000_create_gold_kpis.sql`.

## Views

### `gold.kpi_active_headcount`

Employees employed on each day (one row per day).

- Counted if hired on or before the day (`recent_hire_date`) and not yet left
  (`term_date` empty, or on/after the day).
- Real employees only. Runs from 1990 to the last day of data.

### `gold.kpi_turnover_trend`

Terminations per month, with voluntary/involuntary split and turnover rate.

- `turnover_rate_pct` = terminations / headcount on the 1st of the month × 100.
- Runs from October 2024 (first termination in the file) to the last month of
  data.

### `gold.kpi_avg_tenure_by_department`

Average tenure in years per department (employee's assigned department).

- Tenure = `recent_hire_date` to `term_date`, or to the last day of data if
  still employed. Includes current staff and leavers.
- 29 of 38 departments have one employee; read with the `employees` column.

## Anomalies

### No terminations before October 2024

Hires go back to 1990, but the file has no terminations before October 2024.
Earlier leavers were likely excluded from the export.

- **Headcount** before October 2024 is undercounted and only rises.
- **Turnover** before October 2024 would show 0, so it starts there.
- **Average tenure** is overstated (22.7 years): shorter-tenure leavers are
  missing.
