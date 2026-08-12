#!/usr/bin/env bash
# Prove private TLS connectivity (SELECT 1) to Managed Postgres from Linas app nodes.
# Default dry-run prints plan; --apply runs probes. Never prints passwords.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/_managed_pg_common.sh"

usage() {
  cat <<EOF
usage: $0 <managed-env-file> [--apply] [--node node01|node02|all]

Env file must define LINAS_WHATSAPP_DATABASE_URL or MANAGED_PG_* connection vars.
Probes use sslmode=require and redact credentials in output.
EOF
}

ENV_FILE=""
TARGET_NODE="all"
APPLY=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply) APPLY=1 ;;
    --node) TARGET_NODE="${2:?}"; shift ;;
    -h|--help) usage; exit 0 ;;
    -*) echo "unknown flag: $1" >&2; usage; exit 2 ;;
    *)
      if [[ -z "$ENV_FILE" ]]; then ENV_FILE="$1"; else echo "unexpected arg: $1" >&2; exit 2; fi
      ;;
  esac
  shift
done

[[ -n "$ENV_FILE" ]] || { usage; exit 2; }
mg_load_env_file "$ENV_FILE"
DSN="$(mg_resolve_managed_dsn)"
mg_refuse_local_dsn "$DSN"
REDACTED="$(mg_redact_dsn "$DSN")"

SSH=(ssh -o BatchMode=yes -o ConnectTimeout=15)

probe_remote() {
  local label="$1" host="$2"
  echo "[managed-pg-tls] probe ${label} (${host}) dsn=${REDACTED}"
  if [[ "$APPLY" -ne 1 ]]; then
    echo "[managed-pg-tls] DRY-RUN: would ssh root@${host} and run SELECT 1 with sslmode=require"
    return 0
  fi
  # Pass DSN via stdin to avoid shell history leakage.
  printf '%s' "$DSN" | "${SSH[@]}" "root@${host}" 'python3 - <<"PY"
import os, subprocess, sys
from urllib.parse import urlparse, unquote, parse_qs, urlencode, urlunparse

raw = sys.stdin.read().strip()
u = urlparse(raw.replace("postgresql+psycopg2", "postgresql"))
q = parse_qs(u.query, keep_blank_values=True)
q["sslmode"] = ["require"]
new_q = urlencode({k: v[0] for k, v in q.items()})
uri = urlunparse((u.scheme, u.netloc, u.path, "", new_q, ""))
host = u.hostname or ""
port = str(u.port or 25060)
user = u.username or ""
db = (u.path or "/").lstrip("/") or "postgres"
os.environ["PGPASSWORD"] = unquote(u.password or "")
cmd = [
    "psql", f"host={host}", f"port={port}", f"user={user}", f"dbname={db}",
    "sslmode=require", "-tAc", "SELECT 1",
]
r = subprocess.run(cmd, capture_output=True, text=True)
if r.returncode != 0:
  err = (r.stderr or r.stdout or "").strip().replace(os.environ.get("PGPASSWORD", ""), "***")
  print(f"FAIL rc={r.returncode} err={err[:300]}", file=sys.stderr)
  raise SystemExit(r.returncode)
val = (r.stdout or "").strip()
print(f"OK select_1={val} host={host}:{port} db={db} sslmode=require")
PY'
}

case "$TARGET_NODE" in
  node01) probe_remote node01 "$NODE01_HOST" ;;
  node02) probe_remote node02 "$NODE02_HOST" ;;
  all)
    probe_remote node01 "$NODE01_HOST"
    probe_remote node02 "$NODE02_HOST"
    ;;
  *) echo "invalid --node value: $TARGET_NODE" >&2; exit 2 ;;
esac

echo "[managed-pg-tls] DONE apply=${APPLY}"
