# API

FastAPI app in `api/`, served by the `api` service in docker-compose.yml
(docs at http://localhost:8000/docs). On every start the service seeds the
`admin` and `viewer` users from `.env` (an upsert), so after changing their
passwords run `docker compose restart api`.

Without Docker, from the project root: `python -m api.seed_users`, then
`uvicorn api.main:app --reload`.

## Tests

`python -m pytest` from the project root. The tests run against the real
database and need the users seeded; the create/delete test removes its own
employee afterwards.

## Authentication

- `POST /auth/token` with a username and password returns a bearer token
  (JWT, valid for `JWT_EXPIRE_MINUTES`). In `/docs`, use **Authorize**.
- Two users, created by `api/seed_users.py` from `.env`: `viewer` can read
  employees and timesheets; `admin` can also create, update and delete
  employees. `/health` needs no token.

## Known limitations

- A wrong username and a wrong password return the same message, but a login
  for an unknown username answers faster (no password check runs), so
  usernames could be guessed from response times.
- The role is read from the token, so a role change takes effect when the
  user's current token expires.
