#!/usr/bin/env bash
# Flip LINAS_WHATSAPP_DATABASE_URL on both Linas app nodes to Managed Postgres (private TLS).
# Default dry-run; --apply writes env + optional restart. Never prints passwords.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/_managed_pg_common.sh"

usage() {
  cat <<EOF
usage: $0 <managed-env-file> [--apply] [--restart]

Updates LINAS_WHATSAPP_DATABASE_URL on node01 (${NODE01_HOST}) and node02 (${NODE02_HOST}).
Refuses localhost / 127.0.0.1 / ${NODE01_PRIV}. Backs up prior env to ${ENV_BACKUP_DIR}/.

managed-env-file must contain the new private DSN (sslmode=require) via:
  LINAS_WHATSAPP_DATABASE_URL=postgresql://...

Options:
  --apply     Write env files (default dry-run)
  --restart   systemctl restart linasbot after env write (requires --apply)
EOF
}

ENV_FILE=""
APPLY=0
RESTART=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply) APPLY=1 ;;
    --restart) RESTART=1 ;;
    -h|--help) usage; exit 0 ;;
    -*) echo "unknown flag: $1" >&2; usage; exit 2 ;;
    *)
      if [[ -z "$ENV_FILE" ]]; then ENV_FILE="$1"; else echo "unexpected arg: $1" >&2; exit 2; fi
      ;;
  esac
  shift
done

[[ -n "$ENV_FILE" ]] || { usage; exit 2; }
if [[ "$RESTART" -eq 1 && "$APPLY" -ne 1 ]]; then
  echo "[managed-pg-cutover] --restart requires --apply" >&2
  exit 2
fi

mg_load_env_file "$ENV_FILE"
NEW_DSN="$(mg_resolve_managed_dsn)"
mg_refuse_local_dsn "$NEW_DSN"
REDACTED="$(mg_redact_dsn "$NEW_DSN")"

SSH=(ssh -o BatchMode=yes -o ConnectTimeout=15)

cutover_node() {
  local node_host="$1" label="$2"
  echo "[managed-pg-cutover] ${label} (${node_host}) new_dsn=${REDACTED} apply=${APPLY} restart=${RESTART}"

  if [[ "$APPLY" -ne 1 ]]; then
    echo "[managed-pg-cutover] DRY-RUN ${label}: discover env via systemd, backup to ${ENV_BACKUP_DIR}/, upsert LINAS_WHATSAPP_DATABASE_URL"
    return 0
  fi

  # Pass DSN as base64 in the remote command (never print; avoid stdin/heredoc collision).
  local dsn_b64
  dsn_b64="$(printf '%s' "$NEW_DSN" | base64 | tr -d '\n')"
  "${SSH[@]}" "root@${node_host}" "DSN_B64='${dsn_b64}' python3 -" <<'PY'
import base64
import os
import re
import shutil
import time
from pathlib import Path
from urllib.parse import urlparse, urlunparse

new_dsn = base64.b64decode(os.environ.get("DSN_B64") or "").decode().strip()
if not new_dsn:
    raise SystemExit("DSN_B64 missing")
blocked_hosts = {"localhost", "127.0.0.1", "10.106.0.3"}
u = urlparse(new_dsn.replace("postgresql+psycopg2", "postgresql"))
host = (u.hostname or "").lower()
if host in blocked_hosts:
    raise SystemExit(f"refused legacy host: {host}")
q = (u.query or "").lower()
if "sslmode=require" not in q and "sslmode=verify" not in q:
    raise SystemExit("DSN must include sslmode=require")

unit = Path("/etc/systemd/system/linasbot.service")
text = unit.read_text() if unit.exists() else ""
m = re.search(r"^EnvironmentFile=-?(.+)$", text, re.M)
candidates = [m.group(1).strip()] if m else []
candidates += ["/opt/linasbot/.env"]
env_path = next((Path(p) for p in candidates if Path(p).is_file()), Path("/opt/linasbot/.env"))

backup_dir = Path("/opt/linasbot_backups/env")
backup_dir.mkdir(parents=True, exist_ok=True)
ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
if env_path.is_file():
    dest = backup_dir / f"{env_path.name}.bak-managed-pg-{ts}"
    shutil.copy2(env_path, dest)
    os.chmod(dest, 0o600)
    print(f"backup={dest}")

key = "LINAS_WHATSAPP_DATABASE_URL"
lines = env_path.read_text().splitlines() if env_path.exists() else []
out, found = [], False
for line in lines:
    if line.startswith(f"{key}="):
        out.append(f"{key}={new_dsn}")
        found = True
    else:
        out.append(line)
if not found:
    out.append(f"{key}={new_dsn}")
if not any(l.startswith("LINAS_WHATSAPP_REQUIRE_SSL=") for l in out):
    out.append("LINAS_WHATSAPP_REQUIRE_SSL=true")
if not any(l.startswith("LINAS_WHATSAPP_DB_SSLMODE=") for l in out):
    out.append("LINAS_WHATSAPP_DB_SSLMODE=require")
env_path.parent.mkdir(parents=True, exist_ok=True)
env_path.write_text("\n".join(out).rstrip() + "\n")
os.chmod(env_path, 0o600)

red_host = u.hostname or ""
if u.port:
    red_host = f"{red_host}:{u.port}"
if u.username:
    red_host = f"{u.username}:***@{red_host}"
print("written", urlunparse((u.scheme, red_host, u.path, "", "", "")))
print("env_path", env_path)
PY

  if [[ "$RESTART" -eq 1 ]]; then
    echo "[managed-pg-cutover] ${label} restarting linasbot..."
    "${SSH[@]}" "root@${node_host}" 'systemctl restart linasbot && sleep 2 && systemctl is-active linasbot'
  fi
}

cutover_node "$NODE01_HOST" node01
cutover_node "$NODE02_HOST" node02

echo "[managed-pg-cutover] DONE apply=${APPLY} restart=${RESTART}"
