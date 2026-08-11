#!/usr/bin/env bash
# End-to-end WhatsApp Cloud Postgres provision + Phase 1 migrate/flags + pilot grant.
# Confirmation-gated. Never prints secrets. Does not send WhatsApp messages.
# Does not invent META_WHATSAPP_EMBEDDED_SIGNUP_CONFIG_ID.
#
# Usage:
#   sudo MODE=PROVISION_WHATSAPP_POSTGRES_AND_PHASE1 bash scripts/prod_whatsapp_cloud_postgres_bootstrap.sh
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$APP_DIR"
MODE="${MODE:-}"

echo "[wa-boot] deployed_sha=$(git rev-parse HEAD 2>/dev/null || echo unknown)"
echo "[wa-boot] mode=${MODE}"

if [ "$MODE" != "PROVISION_WHATSAPP_POSTGRES_AND_PHASE1" ]; then
  echo "[wa-boot] BLOCKED: unknown mode=${MODE}"
  exit 2
fi

chmod +x \
  scripts/prod_provision_whatsapp_postgres.sh \
  scripts/prod_whatsapp_pg_backup.sh \
  scripts/prod_whatsapp_cloud_migrate.sh \
  scripts/prod_apply_whatsapp_cloud_phase1_flags.sh \
  scripts/prod_whatsapp_grant_pilot.sh \
  scripts/prod_whatsapp_db_probe.sh 2>/dev/null || true

echo "[wa-boot] step=provision_postgres"
bash scripts/prod_provision_whatsapp_postgres.sh

echo "[wa-boot] step=migrate"
bash scripts/prod_whatsapp_cloud_migrate.sh

# Capture alembic current revision (no secrets).
PYTHON_CMD="python3"
[ -x "$APP_DIR/venv/bin/python" ] && PYTHON_CMD="$APP_DIR/venv/bin/python"
load_env_file() {
  local f="$1"
  if [ -f "$f" ]; then
    set -a
    # shellcheck disable=SC1090
    source "$f"
    set +a
  fi
}
load_env_file "/opt/linasbot/.env"
load_env_file "$APP_DIR/.env"
REV="$("$PYTHON_CMD" -m alembic current 2>/dev/null | awk '{print $1}' | tail -n 1 || true)"
echo "[wa-boot] alembic_current=${REV:-unknown}"

echo "[wa-boot] step=phase1_flags"
bash scripts/prod_apply_whatsapp_cloud_phase1_flags.sh

echo "[wa-boot] step=health_ready"
curl -fsS https://linasaibot.com/api/ready >/tmp/ready.json
curl -fsS https://linasaibot.com/api/health >/tmp/health.json
"$PYTHON_CMD" - <<'PY'
import json
from pathlib import Path
ready = json.loads(Path("/tmp/ready.json").read_text(encoding="utf-8"))
health = json.loads(Path("/tmp/health.json").read_text(encoding="utf-8"))
assert ready.get("ok") is True, ready
assert health.get("ok") is True, health
jq = ready.get("checks", {}).get("job_queue", {})
assert jq.get("redis_required") is not True, jq
print("[wa-boot] ready_ok=true health_ok=true redis_required=", jq.get("redis_required"))
PY

echo "[wa-boot] step=db_ping_and_reconciliation"
"$PYTHON_CMD" - <<'PY'
import os
from pathlib import Path

def load(path: str) -> None:
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip("'").strip('"'))

for path in ("/opt/linasbot/.env", "/opt/linasbot/linaslaserbot-2.7.22/.env"):
    load(path)

from db.session import ping_whatsapp_db, reset_engine_for_tests
from services.whatsapp_cloud.legacy_isolation import assert_no_monty_cloud_dual_bind

reset_engine_for_tests()
ping = ping_whatsapp_db()
assert ping.get("configured") is True and ping.get("reachable") is True and ping.get("status") == "ok", ping
print("[wa-boot] whatsapp_db_health=", ping)
recon = assert_no_monty_cloud_dual_bind()
assert recon.get("ok") is True and recon.get("overlap") is False, recon
print("[wa-boot] reconciliation_ok=", recon)
PY

echo "[wa-boot] step=grant_pilot"
TENANT_ID=linas REASON=whatsapp_cloud_phase1_internal_pilot bash scripts/prod_whatsapp_grant_pilot.sh

echo "[wa-boot] step=probe_presence"
bash scripts/prod_whatsapp_db_probe.sh || true

# Embedded Signup config_id gate — do not invent a value.
"$PYTHON_CMD" - <<'PY'
from pathlib import Path

def merged_env():
    out = {}
    for path in ("/opt/linasbot/.env", "/opt/linasbot/linaslaserbot-2.7.22/.env"):
        p = Path(path)
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            k, v = s.split("=", 1)
            out.setdefault(k.strip(), v.strip().strip("'").strip('"'))
    return out

env = merged_env()
cfg = (env.get("META_WHATSAPP_EMBEDDED_SIGNUP_CONFIG_ID") or "").strip()
pub = (env.get("WHATSAPP_CLOUD_PUBLIC_AVAILABILITY") or "").strip().lower()
print(f"[wa-boot] WHATSAPP_CLOUD_PUBLIC_AVAILABILITY={pub or 'unset'}")
print(f"[wa-boot] META_WHATSAPP_EMBEDDED_SIGNUP_CONFIG_ID present={bool(cfg)} len={len(cfg)}")
if not cfg:
    print("[wa-boot] STOP: META_WHATSAPP_EMBEDDED_SIGNUP_CONFIG_ID missing (human Meta Console required; not inventing)")
    raise SystemExit(78)
print("[wa-boot] COMPLETE_OK")
PY
