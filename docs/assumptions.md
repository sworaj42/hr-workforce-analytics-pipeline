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
