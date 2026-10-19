# Indexing

## Method

Indexes are chosen from the queries, not the tables. A column gets an index when
a query filters or joins on it, no primary key or unique index already starts
with it, the table is large, and the filter keeps a small share of the rows.
Each candidate was measured with `EXPLAIN (ANALYZE, BUFFERS)` before and after.

## Already covered

- Employee lookups: `silver.employee` primary key (`client_employee_id`).
- One employee's timesheets: first column of the `silver.timesheet` primary key
  (`client_employee_id, punch_in_datetime`).
- Fact to employee: first column of the `gold.fact_timesheet` primary key
  (`employee_key, punch_in_datetime`).
- KPI views: they aggregate whole tables, so they read every row anyway.
- `silver.employee` has 50 rows; a full read is already instant.

## Added

`migrations/20261020120000_add_apply_date_indexes.sql`:

| Index | Used by |
|---|---|
| `silver.timesheet (punch_apply_date)` | `GET /timesheets` date range; silver window delete; the gold fact insert's read |
| `gold.fact_timesheet (punch_apply_date)` | gold window delete |

## Evidence

Second of two runs, data in memory. Window start 2025-09-16 (latest punch date
minus 30 days), which covers 111,811 of 381,732 rows (29%). Deletes ran inside
a rolled-back transaction.

**a. `GET /timesheets`, one week (22–28 Sep 2025), first page of 100**

| | Plan | Rows read | Buffers | Time |
|---|---|---|---|---|
| Before | Parallel Seq Scan + sort | 381,732 | 9,156 | 27.7 ms |
| After | Index Scan + incremental sort | 4,977 | 3,949 | 2.8 ms |

**b1. Silver window delete**

| | Plan | Rows read | Buffers (scan) | Time |
|---|---|---|---|---|
| Before | Seq Scan | 381,732 | 9,052 | 112 ms |
| After | Bitmap Index Scan | 111,811 | 7,352 | 116 ms |

**b2. Gold window delete**

| | Plan | Rows read | Buffers (scan) | Time |
|---|---|---|---|---|
| Before | Seq Scan | 381,732 | 7,408 | 116 ms |
| After | Bitmap Index Scan | 111,811 | 6,877 | 97 ms |

**b3. Gold fact insert, reading the window from silver**

| | Plan | Rows read | Buffers | Time |
|---|---|---|---|---|
| Before | Seq Scan | 381,732 | 9,163 | 92 ms |
| After | Bitmap Index Scan | 111,811 | 7,463 | 76 ms |

## Finding

- The index pays off for narrow ranges: the API's week page reads 5k rows
  instead of 382k and is about 10x faster.
- For the 30-day window (29% of rows) Postgres uses a bitmap scan: it reads the
  matching row locations from the index, then visits only those table pages in
  order. The window is recent data at the end of the table, so fewer pages are
  read, but the time barely changes, because most of the work is deleting
  111k rows, not finding them. The window is not the reason for the index.
- Cost: each index is about 2.6 MB and is updated on every insert and delete.
