#!/usr/bin/env bash
# Provision localhost-only PostgreSQL for Linas WhatsApp Cloud SoT.
# Idempotent. Never prints passwords or full DSNs.
# Usage: sudo bash scripts/prod_provision_whatsapp_postgres.sh
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BACKUP_DIR="${LINAS_WHATSAPP_PG_BACKUP_DIR:-/opt/linasbot_backups/whatsapp_pg}"
DB_NAME="${LINAS_WHATSAPP_PG_DB:-linas_whatsapp}"
DB_USER="${LINAS_WHATSAPP_PG_USER:-linas_whatsapp}"
SECRET_FILE="/root/.linas_whatsapp_pg_password"
export DEBIAN_FRONTEND=noninteractive

echo "[wa-pg] deployed_sha=$(git -C "$APP_DIR" rev-parse HEAD 2>/dev/null || echo unknown)"
echo "[wa-pg] start provision db=${DB_NAME} user=${DB_USER}"

if ! command -v apt-get >/dev/null 2>&1; then
  echo "[wa-pg] BLOCKED: apt-get missing (expected Debian/Ubuntu prod host)"
  exit 2
fi

apt-get update -y
apt-get install -y postgresql postgresql-contrib postgresql-client

systemctl enable postgresql
systemctl start postgresql
systemctl is-active --quiet postgresql
echo "[wa-pg] postgresql_service=active"

# Force localhost-only bind (never 0.0.0.0 / *).
PG_CONF="$(sudo -u postgres psql -tAc "SHOW config_file" | tr -d '[:space:]')"
PG_HBA="$(sudo -u postgres psql -tAc "SHOW hba_file" | tr -d '[:space:]')"
if [ -z "$PG_CONF" ] || [ ! -f "$PG_CONF" ]; then
  echo "[wa-pg] BLOCKED: could not resolve postgresql config_file"
  exit 2
fi
echo "[wa-pg] config_file_set=true hba_file_set=true"

python3 - "$PG_CONF" <<'PY'
from pathlib import Path
import re
import sys
path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
# Prefer explicit localhost bind.
if re.search(r"^\s*listen_addresses\s*=", text, re.M):
    text = re.sub(
        r"^\s*listen_addresses\s*=\s*.*$",
        "listen_addresses = 'localhost'",
        text,
        count=1,
        flags=re.M,
    )
else:
    text += "\nlisten_addresses = 'localhost'\n"
path.write_text(text, encoding="utf-8")
print("[wa-pg] listen_addresses=localhost")
PY

python3 - "$PG_HBA" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
desired = [
    "# Linas WhatsApp Cloud — localhost / peer only (managed)",
    "local   all             postgres                                peer",
    "local   all             all                                     peer",
    "host    all             all             127.0.0.1/32            scram-sha-256",
    "host    all             all             ::1/128                 scram-sha-256",
]
# Keep file focused: rewrite managed block; drop any 0.0.0.0 / wide CIDR host lines.
raw = path.read_text(encoding="utf-8").splitlines()
kept = []
for line in raw:
    s = line.strip()
    if s.startswith("#") or not s:
        kept.append(line)
        continue
    lower = s.lower()
    if "0.0.0.0/0" in lower or "::/0" in lower:
        print("[wa-pg] removed_wide_hba_line=true")
        continue
    # Drop previous host lines; we rewrite localhost-only host rules below.
    if lower.startswith("host"):
        continue
    if lower.startswith("local"):
        continue
    kept.append(line)
path.write_text("\n".join(kept).rstrip() + "\n\n" + "\n".join(desired) + "\n", encoding="utf-8")
print("[wa-pg] pg_hba=localhost_or_peer_only")
PY

systemctl reload postgresql || systemctl restart postgresql
sleep 1

# Confirm not publicly bound.
LISTEN_OUT="$(ss -lntp 2>/dev/null | grep -E ':5432\b' || true)"
echo "[wa-pg] listen_5432_raw<<EOF"
echo "${LISTEN_OUT:-no_listen_5432}"
echo "EOF"
if echo "$LISTEN_OUT" | grep -Eq '0\.0\.0\.0:5432|\*:5432|\[::\]:5432'; then
  echo "[wa-pg] BLOCKED: postgres appears bound on a public interface"
  exit 2
fi
if ! echo "$LISTEN_OUT" | grep -Eq '127\.0\.0\.1:5432|\[::1\]:5432|localhost'; then
  # Some distros show "127.0.0.1:5432"; accept also userspace postgres socket-only + TCP local.
  if ! pg_isready -h 127.0.0.1 -p 5432 >/dev/null 2>&1; then
    echo "[wa-pg] BLOCKED: postgres not reachable on 127.0.0.1:5432"
    exit 2
  fi
fi
echo "[wa-pg] localhost_ready=true"

# Firewall evidence (do not open 5432).
if command -v ufw >/dev/null 2>&1; then
  UFW_OUT="$(ufw status 2>/dev/null || true)"
  if echo "$UFW_OUT" | grep -Eiq '5432'; then
    echo "[wa-pg] BLOCKED: ufw mentions 5432 — refuse public exposure risk"
    exit 2
  fi
  echo "[wa-pg] firewall_ufw_5432=not_open"
else
  echo "[wa-pg] firewall_ufw=not_installed"
fi

# Strong password: reuse existing secret file if present; never echo it.
umask 077
if [ -f "$SECRET_FILE" ] && [ -s "$SECRET_FILE" ]; then
  DB_PASS="$(tr -d '\n' < "$SECRET_FILE")"
  echo "[wa-pg] password_source=existing_secret_file"
else
  DB_PASS="$(openssl rand -base64 36 | tr -d '\n=/+' | head -c 40)"
  printf '%s\n' "$DB_PASS" > "$SECRET_FILE"
  chmod 600 "$SECRET_FILE"
  echo "[wa-pg] password_source=generated_secret_file"
fi

# Create role + database with least privilege (CONNECT + schema ownership for migrate).
sudo -u postgres env DB_USER="$DB_USER" DB_PASS="$DB_PASS" DB_NAME="$DB_NAME" python3 - <<'PY'
import os
import subprocess

user = os.environ["DB_USER"]
password = os.environ["DB_PASS"]
db = os.environ["DB_NAME"]

def psql(sql: str, database: str = "postgres") -> str:
    return subprocess.check_output(
        ["psql", "-d", database, "-v", "ON_ERROR_STOP=1", "-tAc", sql],
        text=True,
    ).strip()

pw = password.replace("'", "''")
u_lit = user.replace("'", "''")
d_lit = db.replace("'", "''")
ident = '"' + user.replace('"', '""') + '"'
dbident = '"' + db.replace('"', '""') + '"'

exists = psql(f"SELECT 1 FROM pg_roles WHERE rolname = '{u_lit}'")
if exists != "1":
    psql(f"CREATE ROLE {ident} LOGIN PASSWORD '{pw}'")
    print("[wa-pg] role_created=true")
else:
    psql(f"ALTER ROLE {ident} WITH LOGIN PASSWORD '{pw}'")
    print("[wa-pg] role_updated=true")

db_exists = psql(f"SELECT 1 FROM pg_database WHERE datname = '{d_lit}'")
if db_exists != "1":
    subprocess.check_call(["createdb", "-O", user, db])
    print("[wa-pg] database_created=true")
else:
    psql(f"ALTER DATABASE {dbident} OWNER TO {ident}")
    print("[wa-pg] database_exists=true")

psql(f"REVOKE ALL ON DATABASE {dbident} FROM PUBLIC")
psql(f"GRANT CONNECT ON DATABASE {dbident} TO {ident}")
psql(f"GRANT ALL ON SCHEMA public TO {ident}; ALTER SCHEMA public OWNER TO {ident};", database=db)
print("[wa-pg] grants=least_privilege_owner")
PY

# Build DSN without printing it. Prefer 127.0.0.1 (never hostname postgres).
DSN="$(
  DB_PASS="$DB_PASS" DB_USER="$DB_USER" DB_NAME="$DB_NAME" python3 - <<'PY'
import os
from urllib.parse import quote_plus
user = os.environ["DB_USER"]
password = quote_plus(os.environ["DB_PASS"])
db = os.environ["DB_NAME"]
print(f"postgresql+psycopg2://{user}:{password}@127.0.0.1:5432/{db}")
PY
)"

upsert_env() {
  local file="$1" key="$2" value="$3"
  python3 - "$file" "$key" "$value" <<'PY'
import pathlib, re, sys
path = pathlib.Path(sys.argv[1])
key = sys.argv[2]
value = sys.argv[3]
text = path.read_text(encoding="utf-8") if path.exists() else ""
pattern = re.compile(rf"^{re.escape(key)}=.*$", re.M)
line = f"{key}={value}"
if pattern.search(text):
    text = pattern.sub(line, text)
else:
    if text and not text.endswith("\n"):
        text += "\n"
    text += line + "\n"
path.write_text(text, encoding="utf-8")
print(f"[wa-pg] upserted path={path} key={key}")
PY
}

ENV_FILES=()
[ -f "/opt/linasbot/.env" ] && ENV_FILES+=("/opt/linasbot/.env")
[ -f "$APP_DIR/.env" ] && ENV_FILES+=("$APP_DIR/.env")
[ -f "/opt/linasbot/linaslaserbot-2.7.22/.env" ] && ENV_FILES+=("/opt/linasbot/linaslaserbot-2.7.22/.env")
if [ "${#ENV_FILES[@]}" -eq 0 ]; then
  ENV_FILES=("/opt/linasbot/.env")
  touch "/opt/linasbot/.env"
  chmod 600 "/opt/linasbot/.env"
fi

for envf in "${ENV_FILES[@]}"; do
  upsert_env "$envf" "LINAS_WHATSAPP_DATABASE_URL" "$DSN"
  # Keep public availability false; do not flip Redis requirement; preserve legacy bridge disable.
  upsert_env "$envf" "WHATSAPP_CLOUD_PUBLIC_AVAILABILITY" "false"
  # Ensure CM bridge disable stays true if already set; set if missing.
  if ! grep -q '^CM_DISABLE_LINAS_LEGACY_BRIDGE=' "$envf" 2>/dev/null; then
    upsert_env "$envf" "CM_DISABLE_LINAS_LEGACY_BRIDGE" "true"
  else
    upsert_env "$envf" "CM_DISABLE_LINAS_LEGACY_BRIDGE" "true"
  fi
  # Explicitly do NOT set LINAS_REQUIRE_REDIS=true. If present as true, leave alone only if already true? mandate: do not set it.
  # Remove accidental true only if we introduced it — we never write it here.
done

# Sanitize evidence (no secrets).
python3 - <<'PY'
from pathlib import Path
from urllib.parse import urlparse
for path in ("/opt/linasbot/.env", "/opt/linasbot/linaslaserbot-2.7.22/.env"):
    p = Path(path)
    if not p.exists():
        continue
    raw = ""
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("LINAS_WHATSAPP_DATABASE_URL="):
            raw = line.split("=", 1)[1].strip().strip("'").strip('"')
            break
    if not raw:
        print(f"[wa-pg] sanitize path={path} unset")
        continue
    parse = raw
    if parse.startswith("postgresql+psycopg2://"):
        parse = "postgresql://" + parse[len("postgresql+psycopg2://"):]
    u = urlparse(parse)
    assert u.hostname in {"127.0.0.1", "localhost"}, u.hostname
    assert (u.path or "").lstrip("/") == "linas_whatsapp"
    print(
        f"[wa-pg] sanitize path={path} scheme={raw.split(':',1)[0]} host={u.hostname!r} "
        f"port={u.port} dbname={(u.path or '/').lstrip('/')!r} user_set={bool(u.username)} password_set={bool(u.password)}"
    )
PY

# Connectivity as app role (password never printed).
PGPASSWORD="$DB_PASS" psql -h 127.0.0.1 -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 -c 'SELECT 1 AS ok;' >/dev/null
echo "[wa-pg] app_role_connect=ok"

# Backup directory + install backup helper + daily cron.
mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"
install -m 0755 "$APP_DIR/scripts/prod_whatsapp_pg_backup.sh" /usr/local/sbin/prod_whatsapp_pg_backup.sh
CRON_FILE="/etc/cron.d/linas-whatsapp-pg-backup"
cat > "$CRON_FILE" <<EOF
# Daily WhatsApp Postgres backup (Linas AI)
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
0 3 * * * root /usr/local/sbin/prod_whatsapp_pg_backup.sh >> /var/log/linas-whatsapp-pg-backup.log 2>&1
EOF
chmod 644 "$CRON_FILE"
echo "[wa-pg] daily_backup_cron=installed"

# Run backup + restore test once now for evidence.
sudo LINAS_WHATSAPP_PG_BACKUP_DIR="$BACKUP_DIR" \
  LINAS_WHATSAPP_PG_DB="$DB_NAME" \
  LINAS_WHATSAPP_PG_USER="$DB_USER" \
  LINAS_WHATSAPP_PG_PASSWORD_FILE="$SECRET_FILE" \
  bash /usr/local/sbin/prod_whatsapp_pg_backup.sh --with-restore-test

echo "[wa-pg] COMPLETE_OK"
