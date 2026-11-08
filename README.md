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

In development, emails (verification and recovery codes) go to the outbox and are printed in the server log; set `MITESPOTTER_MAILER=resend` and `MITESPOTTER_RESEND_API_KEY` to send them. Google sign-in needs `MITESPOTTER_GOOGLE_CLIENT_ID` and `MITESPOTTER_GOOGLE_CLIENT_SECRET`. POST requests need the `x-csrftoken` header, copied from the `mitespotter_csrf` cookie.

User-facing text lives in `src/mitespotter_api/messages.toml` and follows [STYLE.md](./STYLE.md).

The OpenAPI schema is at `/api/schema` (`/api/schema/openapi.json` for the frontend's generated types).

## Run the public dev server

The team's dev server: a systemd service behind a Cloudflare named tunnel on a fixed hostname (here `dev.mitespotter.org`). It is on the public internet, so it runs with `MITESPOTTER_ENV=prod`. The steps are the same on a laptop and on the VPS (Ubuntu or Debian with systemd); to move it later, set it up on the VPS and run the tunnel there instead. On a laptop, give the server its own clone: the service holds port 6776 and runs whatever branch that checkout is on. You need uv, Postgres 16 with its client (`psql`), and [cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/).

1. **Database.** A database and user of its own (`install.sh` never creates them):
   ```shell
   sudo -u postgres createuser --pwprompt mitespotter_dev
   sudo -u postgres createdb --owner mitespotter_dev mitespotter_dev
   ```
2. **Tunnel.** Create it, route the hostname to it, and run it as a service:
   ```shell
   cloudflared tunnel login
   cloudflared tunnel create mitespotter-dev
   cloudflared tunnel route dns mitespotter-dev dev.mitespotter.org
   sudo mkdir -p /etc/cloudflared
   sudo cp ~/.cloudflared/<TUNNEL-ID>.json /etc/cloudflared/
   sudo cp deploy/cloudflared.example.yml /etc/cloudflared/config.yml   # then set <TUNNEL-ID>
   sudo cloudflared service install
   ```
   Only `/api/*` is routed; everything else is a 404.
3. **Google.** In Google Cloud Console, create an OAuth client of type *Web application* with the redirect URI `https://dev.mitespotter.org/api/auth/google/callback`. Leave the consent screen in *Testing* and add your Gmail as a test user.
4. **Resend.** Create an API key. Until a domain is verified, send from `onboarding@resend.dev`: Resend then only delivers to the Resend account owner's own address.
5. **Settings.** `cp deploy/dev.env.example deploy/dev.env` and fill it in (secret key, database password, Resend key, Google client).
6. **Install.** `deploy/install.sh` as the user the service should run as (it uses sudo for systemd; `--dry-run` shows what it would do). It syncs dependencies, checks the settings, migrates, installs `mitespotter-api.service` and the nightly `mitespotter-cleanup.timer`, and (re)starts the API. Run it again after every `git pull`.
7. **Check.** `curl https://dev.mitespotter.org/api/health`. Logs: `journalctl -u mitespotter-api -f`. Try every account flow from your phone at `https://dev.mitespotter.org/api/dev` (`MITESPOTTER_DEV_PAGE`: on by default outside prod, off in prod, on in `dev.env.example`).

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

Tests that need Postgres create and drop their own uniquely named databases on that server, and are skipped when the variable is unset. Coverage must be at least 85% for every file, measured with Postgres; CI enforces it (`--cov-fail-under=85` and `tools/check_coverage.py`).
