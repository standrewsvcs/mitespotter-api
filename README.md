# mitespotter-api

Mitespotter's user, image & annotation database API. Every endpoint is under `/api`; files are served from Cloudflare R2 (local disk in development).

See [planning.md](./planning.md) for the specification and deployment.

## Getting Started

You will need [uv](https://docs.astral.sh/uv/) and a running PostgreSQL 16 database.

```shell
uv sync
cp .env.example .env
sed -i 's#REPLACE_URL#postgresql+psycopg://<user>:<password>@localhost/mitespotter#' .env
export UV_ENV_FILE=.env
uv run litestar --app mitespotter_api.app:app database upgrade   # apply migrations
uv run mitespotter-api                                           # http://127.0.0.1:6776/api/health
```

The OpenAPI schema is at `/api/schema` (`/api/schema/openapi.json` for the frontend's generated types).

## Migrations

The schema is only changed through Alembic, via advanced-alchemy's Litestar CLI. After editing `src/mitespotter_api/models.py`:

```shell
uv run litestar --app mitespotter_api.app:app database make-migrations -m "Describe the change" --autogenerate
uv run litestar --app mitespotter_api.app:app database upgrade
```

Review every generated revision, and make sure it downgrades.

## Tests

```shell
MITESPOTTER_TEST_DATABASE_URL=postgresql+psycopg://<user>:<password>@localhost/postgres uv run pytest
```

Tests that need Postgres create and drop their own uniquely named databases on that server, and are skipped when the variable is unset. Coverage must be at least 85% for every file; CI checks this with `tools/check_coverage.py`.
