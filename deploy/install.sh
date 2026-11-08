#!/usr/bin/env bash
# deploy/install.sh
# Install or update the public dev server: dependencies, migrations, systemd units.
# Run from the checkout as the user the service runs as; sudo is used for systemd only.
# Safe to re-run: it is also how you deploy a new commit (git pull, then this).
#
#   deploy/install.sh [--dry-run] [--env-file PATH]    (default env file: deploy/dev.env)
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
ENV_FILE="$REPO_DIR/deploy/dev.env"
DRY_RUN=0
UNITS=(mitespotter-api.service mitespotter-cleanup.service mitespotter-cleanup.timer)

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --env-file) ENV_FILE="${2:?--env-file needs a path}"; shift ;;
    -h|--help) sed -n '2,7p' "$0"; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
  shift
done

die() { echo "error: $*" >&2; exit 1; }
step() { echo; echo "==> $*"; }
run() {
  echo "+ $*"
  if [[ $DRY_RUN -eq 0 ]]; then "$@"; fi
}

postgres_help() {
  cat >&2 <<'EOF'

Could not migrate the database. This script never creates databases; as a Postgres superuser:
  sudo -u postgres createuser --pwprompt mitespotter_dev
  sudo -u postgres createdb --owner mitespotter_dev mitespotter_dev
then check MITESPOTTER_DATABASE_URL in the env file and run this script again.
EOF
}

# The service would run as whoever runs this; it must not be root
if [[ $EUID -eq 0 ]]; then
  [[ $DRY_RUN -eq 1 ]] || die "run as the service user, not root (sudo is used where needed)"
  echo "warning: running as root; a real install refuses to" >&2
fi

step "Checking prerequisites"
need() { command -v "$1" >/dev/null || die "$1 not found: $2"; }
need uv "install it from https://docs.astral.sh/uv/getting-started/installation/"
need psql "install the Postgres 16 client (apt install postgresql-client-16)"
need cloudflared "install it from https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/"
if [[ $DRY_RUN -eq 0 ]]; then
  need sudo "it is needed to install the systemd units"
  need systemctl "this needs a systemd machine (Ubuntu or Debian)"
fi
UV="$(command -v uv)"
UV_CACHE_DIR="$(uv cache dir 2>/dev/null)"

[[ -f "$ENV_FILE" ]] || die "$ENV_FILE not found: copy deploy/dev.env.example to it and fill it in"
ENV_FILE="$(cd "$(dirname "$ENV_FILE")" && pwd -P)/$(basename "$ENV_FILE")"
# Unit files split on whitespace, and the paths go through sed: keep them plain
for path in "$REPO_DIR" "$ENV_FILE" "$UV" "$UV_CACHE_DIR"; do
  [[ "$path" =~ ^[A-Za-z0-9._/+-]+$ ]] || die "unsupported characters in path: $path"
done
echo "checkout $REPO_DIR, env file $ENV_FILE, user $(id -un)"

cd "$REPO_DIR"

step "Installing dependencies"
run chmod 600 "$ENV_FILE"  # it holds the secret key and API keys
run uv sync --frozen

step "Checking the env file"
# Fails on anything config.py rejects; then insists on prod, which also turns auto-reload off
run uv run --frozen --env-file "$ENV_FILE" python -c '
from mitespotter_api.config import config
assert config.is_production and not config.debug, "set MITESPOTTER_ENV=prod and MITESPOTTER_DEBUG=false"
assert config.host == "127.0.0.1", "MITESPOTTER_HOST must be 127.0.0.1: cloudflared is the only way in"
assert config.cookie_secure, "MITESPOTTER_PUBLIC_URL must be the https tunnel hostname"
print("ok:", config.public_url)
'

step "Migrating the database"
if ! run uv run --frozen --env-file "$ENV_FILE" litestar --app mitespotter_api.app:app database upgrade --no-prompt; then
  postgres_help
  exit 1
fi

step "Installing systemd units"
RENDERED="$(mktemp -d)"
trap 'rm -rf "$RENDERED"' EXIT
for unit in "${UNITS[@]}"; do
  sed -e "s|@USER@|$(id -un)|g" -e "s|@GROUP@|$(id -gn)|g" -e "s|@REPO_DIR@|$REPO_DIR|g" \
      -e "s|@ENV_FILE@|$ENV_FILE|g" -e "s|@UV@|$UV|g" -e "s|@UV_CACHE_DIR@|$UV_CACHE_DIR|g" \
      "$REPO_DIR/deploy/$unit" > "$RENDERED/$unit"
  if grep -q '@[A-Z_]*@' "$RENDERED/$unit"; then die "unrendered placeholder in $unit"; fi
  if [[ $DRY_RUN -eq 1 ]]; then echo "--- $unit"; grep -v '^#' "$RENDERED/$unit" | grep .; fi
  run sudo install -m 644 "$RENDERED/$unit" "/etc/systemd/system/$unit"
done
run sudo systemctl daemon-reload
run sudo systemctl enable --now mitespotter-cleanup.timer
# restart, not just start, so a re-run picks up new code
run sudo systemctl enable mitespotter-api.service
run sudo systemctl restart mitespotter-api.service

step "Done"
if [[ $DRY_RUN -eq 0 ]] && ! systemctl is-active --quiet cloudflared; then
  echo "cloudflared is not running as a service: see README \"Run the public dev server\"."
fi
cat <<EOF
Logs:   journalctl -u mitespotter-api -f
Timer:  systemctl list-timers mitespotter-cleanup.timer
Check:  curl http://127.0.0.1:6776/api/health, then https://<your host>/api/health
EOF
