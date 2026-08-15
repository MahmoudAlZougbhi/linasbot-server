#!/usr/bin/env bash
# Safe PostgreSQL migrate for WhatsApp Cloud coexistence tables.
# Fail closed: refuses SQLite, missing URL, or non-PostgreSQL schemes.
# Never prints secret values. Run on production after deploy of WhatsApp code.
#
# Usage (on server, as the deploy user / root with app env loaded):
#   bash scripts/prod_whatsapp_cloud_migrate.sh
#
set -euo pipefail

# shellcheck source=scripts/ha/require_production_mutation_guard.sh
source /opt/linasbot/scripts/ha/require_production_mutation_guard.sh
linas_require_production_mutation_guard "scripts/prod_whatsapp_cloud_phase1_ops.sh"

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$APP_DIR"

echo "[wa-migrate] deployed_sha=$(git rev-parse HEAD 2>/dev/null || echo unknown)"

load_env_file() {
  local f="$1"
  if [ -f "$f" ]; then
    set -a
    # shellcheck disable=SC1090
    source "$f"
    set +a
    echo "[wa-migrate] env_file_loaded=true path=$f"
  fi
}

# Only the canonical root EnvironmentFile is authoritative in production.
load_env_file "/opt/linasbot/.env"

URL="${LINAS_WHATSAPP_DATABASE_URL:-${DATABASE_URL:-}}"
if [ -z "$URL" ]; then
  echo "[wa-migrate] BLOCKED: LINAS_WHATSAPP_DATABASE_URL (or DATABASE_URL) is unset"
  exit 2
fi

SCHEME="${URL%%:*}"
case "$SCHEME" in
  postgresql|postgresql+psycopg2) ;;
  *)
    echo "[wa-migrate] BLOCKED: unsupported scheme=$SCHEME (PostgreSQL required; SQLite forbidden)"
    exit 2
    ;;
esac

if [ "${LINAS_WHATSAPP_ALLOW_SQLITE:-}" = "true" ]; then
  echo "[wa-migrate] BLOCKED: LINAS_WHATSAPP_ALLOW_SQLITE=true is not permitted for production migrate"
  exit 2
fi

PYTHON_CMD="python3"
command -v python3.11 &>/dev/null && PYTHON_CMD="python3.11"
if [ -x "$APP_DIR/venv/bin/python" ]; then
  PYTHON_CMD="$APP_DIR/venv/bin/python"
fi

echo "[wa-migrate] alembic_upgrade=head"
"$PYTHON_CMD" -m alembic upgrade head
echo "[wa-migrate] COMPLETE_OK"
