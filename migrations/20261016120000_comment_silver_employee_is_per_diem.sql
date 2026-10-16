-- Document the is_per_diem rule on the column itself, so it shows in \d+ and
-- database tools. Added as a new migration because applied migrations are
-- never edited; this supersedes the code comment in the silver employee
-- migration. COMMENT ON replaces any previous comment, so rerunning is safe.

COMMENT ON COLUMN silver.employee.is_per_diem IS
    'Derived in the transform: the source flag is_per_deim when it holds a '
    'recognized value, otherwise job_title ending in ''- PD''. The title rule '
    'is an assumption accepted by the data provider and documented in '
    'docs/assumptions.md, with its evidence.';
