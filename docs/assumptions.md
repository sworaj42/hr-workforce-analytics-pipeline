# Assumptions and data findings

**Assumptions** are rules we apply where the source does not say. Each one is
stated so it can be checked or replaced. **Data findings** are facts observed
in the source data.

## Assumptions

### Per-diem employees (`is_per_diem`)
- The source column `is_per_deim` is empty for all 50 employees, so per-diem
  status is derived from the job title only: a title ending in `- PD` means
  per diem. An employee with no job title is not per diem.
- Evidence: all 3 `Variable_time` employees have `- PD` titles (a 4th `- PD`
  title belongs to a `Part_time` employee). The only one of them with shifts
  (`00080`) books all 3 under the `Per Diem` pay code, in the new timekeeping
  system (October 2025). No other employee uses that pay code.
- Accepted by the data provider as an assumption.

### Deleted employees (`is_deleted`)
- Delete is not termination: a leaver gets a `term_date` and stays in
  historical KPIs; a deleted record shouldn't have existed (test or
  duplicate), so it's removed from all HR KPIs.
- A newer employee file overwrites API edits and API-created rows with the
  same ID, but never undoes a delete.
- After a full reload, real employees no longer in silver are marked deleted
  in gold, so they leave the HR KPIs while their past punches keep a valid
  employee.

## Data findings

### The employee file is de-identified
- The data provider de-identified the employee file before export. Names,
  contact details and address fields are masked, empty or placeholders.
- These fields are not used in analysis (confirmed by the data provider), so
  the de-identified, masked and empty fields are dropped at bronze -> silver.
  Bronze keeps the full record as delivered.

### `anniversary_date`
- For the 6 terminated employees it equals `term_date` + 1 day: a system
  artifact, not a service anniversary.
- For the 44 active employees it falls on the same month and day as
  `recent_hire_date`, but the latest one is in 2022, so it is not kept current.
- Not used in analysis.

### Worked time (`is_worked` on `gold.fact_timesheet`)
- Worked = clocked shift time.
- Rows starting at exactly 00:00 are booked entries (time off, meetings,
  training, pay premiums), except the four regular shift codes (`Hourly`,
  `Exempt`, `normal_worked`, `Per Diem`), so real shifts starting at midnight
  still count.
- Evidence: all 40,974 leave-code rows start at 00:00; only 5 midnight rows
  have a schedule; 54 midnight rows carry a regular shift code and are kept as
  worked.
- Verified on the old system only; new-system extracts contain no time-off
  rows. A shift under another code starting exactly at midnight would be
  treated as a booking.

### Test employee in the timesheets
- The source timesheets contain a test employee, `TEST2` (4 punches). It is
  not in the employee file, so gold keeps it as an inferred employee.

### API edits and department names
- `dim_department` takes each department's name from the latest file. An API
  edit to a file employee's `department_name` keeps that employee's file
  timestamp, so it can become the department's name in `dim_department`.
