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

### `gold.kpi_early_attrition_rate`

Share of all employees on file who left within 90 days of their most recent
hire (one row).

- `window_days` (90) sets what counts as early.
- Usually measured on a recent hiring cohort, but the newest hire is from
  2022, so no recent cohort exists.
- Result is 0% under any definition (see Anomalies).

### `gold.kpi_avg_working_hours`

Average worked hours per employee per day worked (one row per employee).

- Daily totals first, since one employee can have several punches in a day.
- Only finished, worked punches (`NOT is_incomplete AND is_worked`);
  worked = clocked shift time, see `docs/assumptions.md`.
- Includes inferred employees (timesheet-only), flagged by `is_inferred`.

### `gold.kpi_rolling_avg_working_hours`

Average worked hours per employee for each day, with a 7-day rolling average
(one row per day with data).

- Rolling value = worked hours / employees over the day and the 6 calendar
  days before it, so busy days weigh more than thin ones.
- Same punches as `kpi_avg_working_hours` (finished, worked).
- `employees_working` drops from July to mid-September: a data gap, not a
  real drop (see Anomalies).

### `gold.kpi_late_arrivals`

Late arrivals per employee: clocked in more than 5 minutes after the scheduled
start (one row per employee).

- Only finished, worked punches with a schedule; `late_rate_pct` = late /
  scheduled shifts × 100. Includes inferred employees, flagged by
  `is_inferred`.
- Exactly 5 minutes late is within the grace time.

### `gold.kpi_early_departures`

Days per employee on which they clocked out more than 5 minutes before the
scheduled end (one row per employee).

- Counted in days, as the brief asks; `scheduled_days` gives the base.
- Same punches as `kpi_late_arrivals`.

### `gold.kpi_overtime`

Overtime days and hours per employee: worked more than 5 minutes beyond the
scheduled shift length (one row per employee).

- Extra time = (punch-out − punch-in) − (scheduled end − scheduled start).
- `overtime_hours` sums the extra time on overtime shifts only.

## Anomalies

### No terminations before October 2024

Hires go back to 1990, but the file has no terminations before October 2024.
Earlier leavers were likely excluded from the export.

- **Headcount** before October 2024 is undercounted and only rises.
- **Turnover** before October 2024 would show 0, so it starts there.
- **Average tenure** is overstated (22.7 years): shorter-tenure leavers are
  missing.
- **Early attrition** shows 0%: short-tenure leavers are missing, and nobody
  was hired recently. The 0% comes from the data, not good onboarding.

### Attendance can't be measured everywhere

Late, early and overtime KPIs need a schedule, and only 43% of punches have
one.

- **From 26 September 2025** there are no schedules (latest extracts), so
  those days aren't covered.
- **August 2025** falls in the low-volume gap (few punches from July to mid
  September).

### Low-volume gap, July to mid-September 2025

Most days in this period have dozens of punches instead of thousands, likely
linked to the timekeeping-system migration. Daily counts drop sharply;
per-employee averages stay comparable, which is why the rolling average uses
them.
