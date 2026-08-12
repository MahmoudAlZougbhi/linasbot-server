#!/usr/bin/env bash
# Restore linas_whatsapp dump into Managed Postgres and verify parity with node01 source.
# Run on node01 (or via ssh from laptop). Default dry-run; --apply executes pg_restore.
# NEVER touches SportBook/BOC databases.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/_managed_pg_common.sh"

usage() {
  cat <<EOF
usage: $0 <managed-env-file> [--apply] [--dump PATH] [--source-env PATH] [--remote node01]

Args:
  managed-env-file   File with MANAGED_PG_* or LINAS_WHATSAPP_DATABASE_URL (private + sslmode=require)

Options:
  --apply            Execute create DB + pg_restore (default dry-run)
  --dump PATH        Custom dump path (default: ${DEFAULT_DUMP_PATH})
  --source-env PATH  Source DSN env for meta compare (default: ${DEFAULT_ENV_FILE})
  --remote node01    ssh root@${NODE01_HOST} and run there (local paths)

Env overrides:
  TARGET_DB_NAME     default ${TARGET_DB_NAME}
  SOURCE_DB_NAME     default ${TARGET_DB_NAME}
EOF
}

ENV_FILE=""
APPLY=0
DUMP_PATH="${DEFAULT_DUMP_PATH}"
SOURCE_ENV="${DEFAULT_ENV_FILE}"
REMOTE=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply) APPLY=1 ;;
    --dump) DUMP_PATH="${2:?}"; shift ;;
    --source-env) SOURCE_ENV="${2:?}"; shift ;;
    --remote) REMOTE="${2:?}"; shift ;;
    -h|--help) usage; exit 0 ;;
    -*) echo "unknown flag: $1" >&2; usage; exit 2 ;;
    *)
      if [[ -z "$ENV_FILE" ]]; then ENV_FILE="$1"; else echo "unexpected arg: $1" >&2; exit 2; fi
      ;;
  esac
  shift
done

[[ -n "$ENV_FILE" ]] || { usage; exit 2; }

run_body() {
  local managed_env="$1" apply="$2" dump_path="$3" source_env="$4"
  export MANAGED_ENV_FILE="$managed_env"
  export RESTORE_APPLY="$apply"
  export RESTORE_DUMP="$dump_path"
  export RESTORE_SOURCE_ENV="$source_env"
  export RESTORE_TARGET_DB="${TARGET_DB_NAME}"
  export RESTORE_SOURCE_DB="${SOURCE_DB_NAME:-$TARGET_DB_NAME}"
  export FORBIDDEN_DB_NAMES_RE

  python3 - <<'PY'
from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse, urlencode, urlunparse

APPLY = os.environ.get("RESTORE_APPLY") == "1"
MANAGED_ENV = Path(os.environ["MANAGED_ENV_FILE"])
DUMP = Path(os.environ["RESTORE_DUMP"])
SOURCE_ENV = Path(os.environ["RESTORE_SOURCE_ENV"])
TARGET_DB = os.environ["RESTORE_TARGET_DB"]
SOURCE_DB = os.environ["RESTORE_SOURCE_DB"]
FORBIDDEN_RE = re.compile(os.environ["FORBIDDEN_DB_NAMES_RE"])


def load_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(errors="replace").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        out[k.strip()] = v.strip().strip("'\"")
    return out


def redact_dsn(raw: str) -> str:
    if "://" not in raw:
        return raw[:120]
    u = urlparse(raw.replace("postgresql+psycopg2", "postgresql"))
    host = u.hostname or ""
    if u.port:
        host = f"{host}:{u.port}"
    if u.username:
        host = f"{u.username}:***@{host}"
    return urlunparse((u.scheme, host, u.path, "", "", ""))


def resolve_managed_dsn(env: dict[str, str]) -> str:
    if env.get("LINAS_WHATSAPP_DATABASE_URL"):
        return env["LINAS_WHATSAPP_DATABASE_URL"]
    if env.get("MANAGED_PG_DATABASE_URL"):
        return env["MANAGED_PG_DATABASE_URL"]
    host = env.get("MANAGED_PG_HOST") or env.get("MG_PG_HOST") or ""
    port = env.get("MANAGED_PG_PORT") or env.get("MG_PG_PORT") or "25060"
    user = env.get("MANAGED_PG_USER") or env.get("MG_PG_USER") or ""
    pw = env.get("MANAGED_PG_PASSWORD") or env.get("MG_PG_PASSWORD") or ""
    db = env.get("MANAGED_PG_DB") or env.get("MG_PG_DB") or TARGET_DB
    if not (host and user and pw):
        raise SystemExit("managed env missing LINAS_WHATSAPP_DATABASE_URL or MANAGED_PG_HOST/USER/PASSWORD")
    from urllib.parse import quote

    return f"postgresql://{quote(user)}:{quote(pw)}@{host}:{port}/{db}?sslmode=require"


def resolve_source_dsn(env: dict[str, str]) -> str:
    raw = env.get("LINAS_WHATSAPP_DATABASE_URL") or env.get("DATABASE_URL") or ""
    if not raw:
        raise SystemExit(f"source env missing LINAS_WHATSAPP_DATABASE_URL: {SOURCE_ENV}")
    u = urlparse(raw.replace("postgresql+psycopg2", "postgresql"))
    return urlunparse((u.scheme, u.netloc, f"/{SOURCE_DB}", u.params, u.query, u.fragment))


def parse_pg(raw: str) -> dict[str, str]:
    u = urlparse(raw.replace("postgresql+psycopg2", "postgresql"))
    q = parse_qs(u.query, keep_blank_values=True)
    return {
        "host": u.hostname or "",
        "port": str(u.port or 5432),
        "user": u.username or "",
        "password": unquote(u.password or ""),
        "dbname": (u.path or "/").lstrip("/") or "postgres",
        "sslmode": (q.get("sslmode") or [""])[0],
    }


def refuse_forbidden_db(name: str) -> None:
    if FORBIDDEN_RE.match(name or ""):
        raise SystemExit(f"refused forbidden database name: {name}")


def refuse_local_managed(pg: dict[str, str]) -> None:
    host = (pg.get("host") or "").lower()
    if host in {"localhost", "127.0.0.1", "10.106.0.3"}:
        raise SystemExit(f"refused local/legacy managed host: {host}")
    ssl = (pg.get("sslmode") or "").lower()
    if ssl not in {"require", "verify-ca", "verify-full"}:
        raise SystemExit("managed connection must use sslmode=require")


def psql_env(pg: dict[str, str], *, admin_db: str | None = None) -> dict[str, str]:
    env = os.environ.copy()
    env["PGPASSWORD"] = pg["password"]
    return env


def run_psql(pg: dict[str, str], sql: str, *, db: str | None = None, capture: bool = True) -> str:
    dbname = db or pg["dbname"]
    cmd = [
        "psql",
        f"host={pg['host']}",
        f"port={pg['port']}",
        f"user={pg['user']}",
        f"dbname={dbname}",
    ]
    if pg.get("sslmode"):
        cmd.append(f"sslmode={pg['sslmode']}")
    cmd += ["-v", "ON_ERROR_STOP=1", "-tAc", sql]
    r = subprocess.run(cmd, env=psql_env(pg), capture_output=capture, text=True)
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "").replace(pg["password"], "***")
        raise RuntimeError(f"psql failed rc={r.returncode}: {err[:400]}")
    return (r.stdout or "").strip()


def list_databases(pg: dict[str, str]) -> list[str]:
    rows = run_psql(pg, "SELECT datname FROM pg_database WHERE datistemplate = false ORDER BY 1", db="postgres")
    return [x.strip() for x in rows.splitlines() if x.strip()]


def collect_meta(pg: dict[str, str], db: str) -> dict:
    meta: dict = {}
    meta["extensions"] = sorted(
        x.strip()
        for x in run_psql(pg, "SELECT extname FROM pg_extension ORDER BY 1", db=db).splitlines()
        if x.strip()
    )
    meta["alembic_version"] = run_psql(pg, "SELECT version_num FROM alembic_version LIMIT 1", db=db)
    tables = [
        x.strip()
        for x in run_psql(
            pg,
            "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY 1",
            db=db,
        ).splitlines()
        if x.strip()
    ]
    meta["tables"] = tables
    meta["table_counts"] = {}
    meta["row_counts"] = {}
    ident_re = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

    def safe_ident(name: str) -> str:
        if not ident_re.match(name):
            raise ValueError(f"unsafe table identifier: {name}")
        return name

    for t in tables:
        meta["table_counts"][t] = int(
            run_psql(pg, f'SELECT COUNT(*) FROM "{safe_ident(t)}"', db=db) or 0
        )
        meta["row_counts"][t] = meta["table_counts"][t]
    meta["sequences"] = sorted(
        x.strip()
        for x in run_psql(
            pg,
            "SELECT sequence_name FROM information_schema.sequences WHERE sequence_schema='public' ORDER BY 1",
            db=db,
        ).splitlines()
        if x.strip()
    )
    meta["indexes"] = sorted(
        x.strip()
        for x in run_psql(
            pg,
            "SELECT indexname FROM pg_indexes WHERE schemaname='public' ORDER BY 1",
            db=db,
        ).splitlines()
        if x.strip()
    )
    meta["constraints"] = sorted(
        x.strip()
        for x in run_psql(
            pg,
            "SELECT conname FROM pg_constraint c JOIN pg_namespace n ON n.oid=c.connamespace "
            "WHERE n.nspname='public' ORDER BY 1",
            db=db,
        ).splitlines()
        if x.strip()
    )
    return meta


def compare_meta(src: dict, dst: dict) -> list[str]:
    errs: list[str] = []
    if src.get("alembic_version") != dst.get("alembic_version"):
        errs.append(f"alembic_version src={src.get('alembic_version')} dst={dst.get('alembic_version')}")
    # extensions: managed may add extras; require source subset present
    src_ext = set(src.get("extensions") or [])
    dst_ext = set(dst.get("extensions") or [])
    missing_ext = sorted(src_ext - dst_ext)
    if missing_ext:
        errs.append(f"extensions missing on target: {missing_ext}")
    if set(src.get("tables") or []) != set(dst.get("tables") or []):
        errs.append(
            f"table set mismatch src={len(src.get('tables') or [])} dst={len(dst.get('tables') or [])}"
        )
    for t in sorted(set(src.get("tables") or []) & set(dst.get("tables") or [])):
        sc = (src.get("row_counts") or {}).get(t)
        dc = (dst.get("row_counts") or {}).get(t)
        if sc != dc:
            errs.append(f"row_count {t}: src={sc} dst={dc}")
    for label, key in (("sequences", "sequences"), ("indexes", "indexes"), ("constraints", "constraints")):
        s_set = set(src.get(key) or [])
        d_set = set(dst.get(key) or [])
        if s_set != d_set:
            errs.append(f"{label} mismatch missing={sorted(s_set - d_set)[:8]} extra={sorted(d_set - s_set)[:8]}")
    return errs


managed_env_map = load_env(MANAGED_ENV)
source_env_map = load_env(SOURCE_ENV)
managed_raw = resolve_managed_dsn(managed_env_map)
source_raw = resolve_source_dsn(source_env_map)
managed_pg = parse_pg(managed_raw)
source_pg = parse_pg(source_raw)

refuse_forbidden_db(TARGET_DB)
refuse_forbidden_db(SOURCE_DB)
refuse_local_managed(managed_pg)

print(f"[managed-pg-restore] apply={APPLY}")
print(f"[managed-pg-restore] managed={redact_dsn(managed_raw)}")
print(f"[managed-pg-restore] source={redact_dsn(source_raw)}")
print(f"[managed-pg-restore] dump={DUMP}")

if not DUMP.is_file():
    raise SystemExit(f"dump missing: {DUMP}")

# Prove managed cluster has no forbidden DB names
admin_pg = dict(managed_pg)
admin_pg["dbname"] = "postgres"
dbs = list_databases(admin_pg)
forbidden = [d for d in dbs if FORBIDDEN_RE.match(d)]
if forbidden:
    raise SystemExit(f"forbidden databases present on managed cluster: {forbidden}")
print(f"[managed-pg-restore] managed_db_inventory count={len(dbs)} (no BOC/SportBook names)")

if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", TARGET_DB):
    raise SystemExit(f"unsafe TARGET_DB: {TARGET_DB}")
exists = run_psql(
    admin_pg,
    f"SELECT 1 FROM pg_database WHERE datname='{TARGET_DB}'",
    db="postgres",
)
if exists.strip() == "1":
    print(f"[managed-pg-restore] target db exists: {TARGET_DB}")
else:
    print(f"[managed-pg-restore] target db missing: {TARGET_DB}")
    if APPLY:
        run_psql(admin_pg, f'CREATE DATABASE "{TARGET_DB}"', db="postgres")
        print(f"[managed-pg-restore] created database {TARGET_DB}")
    else:
        print("[managed-pg-restore] DRY-RUN: would CREATE DATABASE")

if APPLY:
    target_pg = dict(managed_pg)
    target_pg["dbname"] = TARGET_DB
    cmd = [
        "pg_restore",
        "-Fc",
        "--no-owner",
        "--no-acl",
        "-h",
        target_pg["host"],
        "-p",
        target_pg["port"],
        "-U",
        target_pg["user"],
        "-d",
        TARGET_DB,
        str(DUMP),
    ]
    env = psql_env(target_pg)
    print("[managed-pg-restore] running pg_restore -Fc ...")
    r = subprocess.run(cmd, env=env)
    if r.returncode not in (0, 1):
        raise SystemExit(f"pg_restore failed rc={r.returncode}")
    print(f"[managed-pg-restore] pg_restore rc={r.returncode} (1=non-fatal warnings)")
else:
    print("[managed-pg-restore] DRY-RUN: would pg_restore -Fc from dump")

# TLS local connection test (sslmode=require)
print("[managed-pg-restore] tls probe (sslmode=require)...")
tls_pg = dict(managed_pg)
tls_pg["dbname"] = TARGET_DB
tls_pg["sslmode"] = "require"
val = run_psql(tls_pg, "SELECT 1", db=TARGET_DB)
print(f"[managed-pg-restore] tls_ok select_1={val}")

print("[managed-pg-restore] collecting source meta ...")
src_meta = collect_meta(source_pg, SOURCE_DB)
print("[managed-pg-restore] collecting target meta ...")
dst_meta = collect_meta(tls_pg, TARGET_DB)

errs = compare_meta(src_meta, dst_meta)
print(
    f"[managed-pg-restore] meta summary tables={len(dst_meta.get('tables') or [])} "
    f"alembic={dst_meta.get('alembic_version')} extensions={dst_meta.get('extensions')}"
)
if errs:
    for e in errs:
        print(f"[managed-pg-restore] VERIFY_FAIL {e}")
    raise SystemExit(1)
print("[managed-pg-restore] VERIFY_PASS extensions/alembic/tables/rows/sequences/indexes/constraints")
PY
}

if [[ -n "$REMOTE" ]]; then
  case "$REMOTE" in
    node01) REMOTE_HOST="$NODE01_HOST" ;;
    *) echo "unsupported --remote value: $REMOTE (use node01)" >&2; exit 2 ;;
  esac
  echo "[managed-pg-restore] remote=${REMOTE_HOST}"
  REMOTE_ENV="/tmp/managed_pg_restore_env.$$"
  scp -o BatchMode=yes -o ConnectTimeout=15 "$ENV_FILE" "root@${REMOTE_HOST}:${REMOTE_ENV}"
  REMOTE_SCRIPT="/opt/linasbot/scripts/ha/managed_pg_restore_verify.sh"
  REMOTE_ARGS=( "$REMOTE_ENV" )
  [[ "$APPLY" -eq 1 ]] && REMOTE_ARGS+=( --apply )
  REMOTE_ARGS+=( --dump "$DUMP_PATH" --source-env "$SOURCE_ENV" )
  if ssh -o BatchMode=yes "root@${REMOTE_HOST}" "test -x '${REMOTE_SCRIPT}'"; then
    ssh -o BatchMode=yes "root@${REMOTE_HOST}" "bash '${REMOTE_SCRIPT}' $(printf '%q ' "${REMOTE_ARGS[@]}")"
  else
    echo "[managed-pg-restore] remote script missing at ${REMOTE_SCRIPT}; run from repo checkout on node01" >&2
    exit 1
  fi
  ssh -o BatchMode=yes "root@${REMOTE_HOST}" "rm -f '${REMOTE_ENV}'" || true
else
  run_body "$ENV_FILE" "$APPLY" "$DUMP_PATH" "$SOURCE_ENV"
fi

echo "[managed-pg-restore] DONE apply=${APPLY}"
