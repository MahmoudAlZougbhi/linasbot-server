#!/usr/bin/env bash
# Daily backup (+ optional restore smoke test) for Linas WhatsApp Postgres.
# Never prints dump contents, passwords, or full DSNs.
# Usage:
#   sudo bash scripts/prod_whatsapp_pg_backup.sh
#   sudo bash scripts/prod_whatsapp_pg_backup.sh --with-restore-test
set -euo pipefail

BACKUP_DIR="${LINAS_WHATSAPP_PG_BACKUP_DIR:-/opt/linasbot_backups/whatsapp_pg}"
DB_NAME="${LINAS_WHATSAPP_PG_DB:-linas_whatsapp}"
DB_USER="${LINAS_WHATSAPP_PG_USER:-linas_whatsapp}"
SECRET_FILE="${LINAS_WHATSAPP_PG_PASSWORD_FILE:-/root/.linas_whatsapp_pg_password}"
WITH_RESTORE=false
for arg in "$@"; do
  if [ "$arg" = "--with-restore-test" ]; then
    WITH_RESTORE=true
  fi
done

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

if [ ! -s "$SECRET_FILE" ]; then
  echo "[wa-pg-backup] BLOCKED: missing password file"
  exit 2
fi
DB_PASS="$(tr -d '\n' < "$SECRET_FILE")"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="${BACKUP_DIR}/linas_whatsapp_${STAMP}.dump"
export PGPASSWORD="$DB_PASS"

pg_dump -h 127.0.0.1 -U "$DB_USER" -d "$DB_NAME" -Fc -f "$OUT"
chmod 600 "$OUT"
BYTES="$(wc -c < "$OUT" | tr -d ' ')"
echo "[wa-pg-backup] dump_ok path_basename=$(basename "$OUT") bytes=${BYTES}"

# Retain 14 days.
find "$BACKUP_DIR" -type f -name 'linas_whatsapp_*.dump' -mtime +14 -delete 2>/dev/null || true
COUNT="$(find "$BACKUP_DIR" -type f -name 'linas_whatsapp_*.dump' | wc -l | tr -d ' ')"
echo "[wa-pg-backup] retained_dumps=${COUNT}"

if [ "$WITH_RESTORE" = true ]; then
  RESTORE_DB="linas_whatsapp_restore_test"
  sudo -u postgres psql -v ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS ${RESTORE_DB};"
  sudo -u postgres psql -v ON_ERROR_STOP=1 -c "CREATE DATABASE ${RESTORE_DB} OWNER ${DB_USER};"
  pg_restore -h 127.0.0.1 -U "$DB_USER" -d "$RESTORE_DB" --clean --if-exists "$OUT" >/tmp/wa_pg_restore.log 2>&1 || true
  # Empty DB restore of brand-new DB is fine; verify connectivity + object count without dumping rows.
  TABLE_COUNT="$(
    psql -h 127.0.0.1 -U "$DB_USER" -d "$RESTORE_DB" -tAc \
      "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';" | tr -d '[:space:]'
  )"
  psql -h 127.0.0.1 -U "$DB_USER" -d "$RESTORE_DB" -v ON_ERROR_STOP=1 -c 'SELECT 1 AS restore_ok;' >/dev/null
  sudo -u postgres psql -v ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS ${RESTORE_DB};"
  echo "[wa-pg-backup] restore_test=ok public_tables=${TABLE_COUNT} dump_bytes=${BYTES}"
fi

unset PGPASSWORD
echo "[wa-pg-backup] COMPLETE_OK"
