# shellcheck shell=bash
# Shared helpers for Managed Postgres HA cutover scripts (source only).
set -euo pipefail

MG_PG_CLUSTER_ID="${MG_PG_CLUSTER_ID:-17d6fb7e-30d7-442a-a716-5c5344639659}"
MG_PG_CLUSTER_NAME="${MG_PG_CLUSTER_NAME:-linas-postgres-prod}"
MG_PG_DROPLET_IDS="${MG_PG_DROPLET_IDS:-510629908,591901417}"
MG_PG_FIREWALL_TAG="${MG_PG_FIREWALL_TAG:-linas}"

NODE01_HOST="${NODE01_HOST:-139.59.167.62}"
NODE02_HOST="${NODE02_HOST:-167.99.89.243}"
NODE01_PRIV="${NODE01_PRIV:-10.106.0.3}"
NODE02_PRIV="${NODE02_PRIV:-10.106.0.4}"

DEFAULT_ENV_FILE="${DEFAULT_ENV_FILE:-/opt/linasbot/.env}"
ENV_BACKUP_DIR="${ENV_BACKUP_DIR:-/opt/linasbot_backups/env}"
DEFAULT_DUMP_PATH="${DEFAULT_DUMP_PATH:-/opt/linasbot_backups/pg/linas_whatsapp_20260812T182822Z.dump}"
TARGET_DB_NAME="${TARGET_DB_NAME:-linas_whatsapp}"

FORBIDDEN_DB_NAMES_RE='(?i)^(sportbook|boc|linaslaser|linas_laser).*$'

mg_apply=0
mg_parse_apply() {
  mg_apply=0
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --apply) mg_apply=1 ;;
      -h|--help) return 2 ;;
      *) return 0 ;;
    esac
    shift
  done
}

mg_redact_dsn() {
  python3 - "$1" <<'PY'
import sys
from urllib.parse import urlparse, urlunparse
raw = sys.argv[1]
if "://" not in raw:
    print(raw[:120])
    raise SystemExit(0)
u = urlparse(raw.replace("postgresql+psycopg2", "postgresql"))
host = u.hostname or ""
if u.port:
    host = f"{host}:{u.port}"
if u.username:
    host = f"{u.username}:***@{host}"
print(urlunparse((u.scheme, host, u.path, "", "", "")))
PY
}

mg_load_env_file() {
  local path="$1"
  [[ -f "$path" ]] || { echo "[managed-pg] env file missing: $path" >&2; return 1; }
  set -a
  # shellcheck disable=SC1090
  source <(python3 - "$path" <<'PY'
import shlex, sys
from pathlib import Path
for line in Path(sys.argv[1]).read_text(errors="replace").splitlines():
    s = line.strip()
    if not s or s.startswith("#") or "=" not in s:
        continue
    k, v = s.split("=", 1)
    k = k.strip()
    v = v.strip().strip("'").strip('"')
    if k:
        print(f"export {k}={shlex.quote(v)}")
PY
)
  set +a
}

mg_resolve_managed_dsn() {
  if [[ -n "${LINAS_WHATSAPP_DATABASE_URL:-}" ]]; then
    printf '%s' "$LINAS_WHATSAPP_DATABASE_URL"
    return 0
  fi
  if [[ -n "${MANAGED_PG_DATABASE_URL:-}" ]]; then
    printf '%s' "$MANAGED_PG_DATABASE_URL"
    return 0
  fi
  local host="${MANAGED_PG_HOST:-${MG_PG_HOST:-}}"
  local port="${MANAGED_PG_PORT:-${MG_PG_PORT:-25060}}"
  local user="${MANAGED_PG_USER:-${MG_PG_USER:-}}"
  local pass="${MANAGED_PG_PASSWORD:-${MG_PG_PASSWORD:-}}"
  local db="${MANAGED_PG_DB:-${MG_PG_DB:-$TARGET_DB_NAME}}"
  if [[ -z "$host" || -z "$user" || -z "$pass" ]]; then
    echo "[managed-pg] need LINAS_WHATSAPP_DATABASE_URL or MANAGED_PG_HOST/USER/PASSWORD in env file" >&2
    return 1
  fi
  python3 - "$user" "$pass" "$host" "$port" "$db" <<'PY'
import sys
from urllib.parse import quote
user, pw, host, port, db = sys.argv[1:6]
print(f"postgresql://{quote(user, safe='')}:{quote(pw, safe='')}@{host}:{port}/{db}?sslmode=require")
PY
}

mg_refuse_local_dsn() {
  python3 - "$1" "$NODE01_PRIV" <<'PY'
import sys
from urllib.parse import urlparse
raw, node01_priv = sys.argv[1], sys.argv[2]
u = urlparse(raw.replace("postgresql+psycopg2", "postgresql"))
host = (u.hostname or "").lower()
blocked = {"localhost", "127.0.0.1", node01_priv}
if host in blocked:
    raise SystemExit(f"refused local/legacy host for managed cutover: {host}")
ssl = (u.query or "").lower()
if "sslmode=require" not in ssl and "sslmode=verify-full" not in ssl and "sslmode=verify-ca" not in ssl:
    raise SystemExit("managed DSN must include sslmode=require (or verify-*)")
PY
}

mg_discover_env_file() {
  local node="$1"
  "${SSH[@]}" "root@${node}" 'python3 - <<"PY"
from pathlib import Path
import re
unit = Path("/etc/systemd/system/linasbot.service")
text = unit.read_text() if unit.exists() else ""
m = re.search(r"^EnvironmentFile=-?(.+)$", text, re.M)
candidates = []
if m:
    candidates.append(m.group(1).strip())
candidates += ["/opt/linasbot/.env", "/etc/linasbot/.env"]
for p in candidates:
    if Path(p).is_file():
        print(p)
        raise SystemExit(0)
raise SystemExit("no env file found")
PY'
}
