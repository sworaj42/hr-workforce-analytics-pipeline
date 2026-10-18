# KPIs

KPI queries are views in the `gold` schema, created by
`migrations/20261018120000_create_gold_kpis.sql`.

## Anomalies

### No terminations before October 2024

The employee file contains no terminations before October 2024, although
hires go back to 1990. Most likely, the export only included current
employees and people who left from October 2024 onward. Employees who left
earlier are missing entirely.

**Effect**

- Headcount before October 2024 is undercounted, and only rises, because
  missing leavers are never counted.
- Turnover before October 2024 would show 0, which isn't real.

**Handling**

Turnover is reported from October 2024. Headcount is shown in full, but values
before October 2024 should be read as "employees still on file", not total
historical staff.
