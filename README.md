# Football Forecast

A fantasy-football forecasting application that projects full-PPR points for NFL
running backs, wide receivers, and tight ends.

See the [product requirements](MRD.md) and the
[approved backend implementation plan](docs/backend-implementation-plan.md) for
scope, forecast defaults, milestone order, and acceptance criteria.

## Local PostgreSQL

The application uses PostgreSQL in development, testing, and production. Local
development runs PostgreSQL 17 in Docker; production will use Supabase Postgres.

Prerequisites (either runtime is sufficient):

- Docker Desktop/Engine with Docker Compose v2
- Podman with `podman-compose`

Start the database and wait for it to become healthy:

```bash
docker compose up -d postgres
docker compose ps
```

With Podman, replace `docker compose` with `podman compose` in these commands.

The first startup creates two databases:

- `football_forecast` for local development
- `football_forecast_test` for integration tests

Copy the backend environment example before starting the API or running tests:

```bash
cp backend/.env.example backend/.env
```

The local development credentials are intentionally committed for convenience.
They must never be reused for a deployed database.

Stop the container while retaining its data:

```bash
docker compose stop postgres
```

If port 5432 is already occupied, choose another host port and update both URLs
in `backend/.env` accordingly:

```bash
POSTGRES_PORT=5433 docker compose up -d postgres
```

Once a Supabase project has been created, align the local PostgreSQL major version
with that project's version before relying on production-specific behavior.
