-- API users. Not HR data, so they get their own schema.
-- Users are added by api/seed_users.py, so no password is ever in a migration.

CREATE SCHEMA IF NOT EXISTS app;

CREATE TABLE IF NOT EXISTS app.api_user (
    username       TEXT  PRIMARY KEY,
    password_hash  TEXT  NOT NULL,                                     -- bcrypt hash, never the password
    role           TEXT  NOT NULL CHECK (role IN ('admin', 'viewer'))  -- admin: CRUD, viewer: read only
);
