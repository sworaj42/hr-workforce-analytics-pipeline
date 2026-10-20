# Setup

Needs Docker with Docker Compose.

1. Copy `.env.example` to `.env` and fill in the empty values and passwords
   (each one has a comment saying how to generate it).
2. Start everything:

   ```
   docker compose up -d
   ```

   On start, `minio-init` uploads the files in `data/` to MinIO, and
   `migrations` creates the warehouse schemas (bronze, silver, gold, app).
   The API and Airflow wait for both to finish.
3. Run the pipeline: in Airflow (http://localhost:8080), trigger `hr_pipeline`.
   The first run loads everything; later runs reload the last
   `INCREMENTAL_WINDOW_DAYS` (trigger with `full_reload` = true to reload all).
   Files are read from MinIO by default; set `SOURCE=local` in `.env` to read
   them straight from `data/` instead (restart Airflow after changing it).

| Service | URL |
|---|---|
| Airflow | http://localhost:8080 |
| API docs | http://localhost:8000/docs |
| MinIO console | http://localhost:9001 |
| Warehouse (Postgres) | localhost:`POSTGRES_HOST_PORT` (5433) |

## Migrations

`migrations/*.sql` are applied in filename order by `pipeline/migrate.py`,
which records each file in `public.schema_migrations` and skips files already
there. To add a change, add a new file with a later timestamp; never edit an
applied one. Run by hand with `docker compose run --rm migrations` (or
`python -m pipeline.migrate` from the project root).
