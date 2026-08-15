#!/usr/bin/env bash
# Read-only diagnostic comparison of an already restored, isolated Managed Postgres database.
# The former in-place restore path is retired: it could overlay an existing database
# and could not prove an atomic restore.  Creation/restoration is now a separate,
# confirmation-gated provider operation; this helper never mutates PostgreSQL
# and deliberately never emits a restore-acceptance PASS.
# NEVER touches SportBook/BOC databases.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/_managed_pg_common.sh"

usage() {
  cat <<EOF
usage: $0 <managed-env-file> --expected-dump-sha256 SHA256 [--dump PATH] [--source-env PATH] [--remote node01]

Args:
  managed-env-file   File with MANAGED_PG_* or LINAS_WHATSAPP_DATABASE_URL (private + sslmode=require)

Options:
  --apply            RETIRED and always refused; this verifier is read-only
  --expected-dump-sha256 SHA256
                     Required SHA-256 of the immutable custom-format dump
  --dump PATH        Custom dump path (default: ${DEFAULT_DUMP_PATH})
  --source-env PATH  Source DSN env for meta compare (default: ${DEFAULT_ENV_FILE})
  --remote node01    ssh root@${NODE01_HOST}; every supplied path must already exist securely there

Env overrides:
  TARGET_DB_NAME     default ${TARGET_DB_NAME}
  SOURCE_DB_NAME     default ${TARGET_DB_NAME}
EOF
}

ENV_FILE=""
APPLY=0
EXPECTED_DUMP_SHA256=""
DUMP_PATH="${DEFAULT_DUMP_PATH}"
SOURCE_ENV="${DEFAULT_ENV_FILE}"
REMOTE=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply) APPLY=1 ;;
    --expected-dump-sha256) EXPECTED_DUMP_SHA256="${2:?}"; shift ;;
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
if [[ "$APPLY" -eq 1 ]]; then
  echo "[managed-pg-restore] REFUSED: legacy in-place restore is retired; restore only into a new isolated database through the confirmed provider runbook" >&2
  exit 2
fi
case "$EXPECTED_DUMP_SHA256" in
  ''|*[!0-9a-f]*)
    echo "[managed-pg-restore] --expected-dump-sha256 must be 64 lowercase hexadecimal characters" >&2
    exit 2
    ;;
esac
if [[ "${#EXPECTED_DUMP_SHA256}" -ne 64 ]]; then
  echo "[managed-pg-restore] --expected-dump-sha256 must be 64 lowercase hexadecimal characters" >&2
  exit 2
fi

run_body() {
  local managed_env="$1" dump_path="$2" source_env="$3"
  export MANAGED_ENV_FILE="$managed_env"
  export RESTORE_DUMP="$dump_path"
  export RESTORE_EXPECTED_DUMP_SHA256="$EXPECTED_DUMP_SHA256"
  export RESTORE_SOURCE_ENV="$source_env"
  export RESTORE_TARGET_DB="${TARGET_DB_NAME}"
  export RESTORE_SOURCE_DB="${SOURCE_DB_NAME:-$TARGET_DB_NAME}"
  export FORBIDDEN_DB_NAMES_RE

  python3 - <<'PY'
from __future__ import annotations

import hashlib
import hmac
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse, urlencode, urlunparse

MANAGED_ENV = Path(os.environ["MANAGED_ENV_FILE"])
DUMP = Path(os.environ["RESTORE_DUMP"])
EXPECTED_DUMP_SHA256 = os.environ["RESTORE_EXPECTED_DUMP_SHA256"]
SOURCE_ENV = Path(os.environ["RESTORE_SOURCE_ENV"])
TARGET_DB = os.environ["RESTORE_TARGET_DB"]
SOURCE_DB = os.environ["RESTORE_SOURCE_DB"]
FORBIDDEN_RE = re.compile(os.environ["FORBIDDEN_DB_NAMES_RE"])


def load_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        info = path.lstat()
    except OSError as exc:
        raise SystemExit(f"required environment file is unavailable: {path}") from exc
    if not path.is_file() or path.is_symlink() or (info.st_mode & 0o777) != 0o600:
        raise SystemExit(f"environment file must be a regular non-symlink mode-0600 file: {path}")
    if os.geteuid() == 0 and (info.st_uid != 0 or info.st_gid != 0):
        raise SystemExit(f"production environment file must be root:root: {path}")
    for line in path.read_text(errors="replace").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        out[k.strip()] = v.strip().strip("'\"")
    return out


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def query_sha256(pg: dict[str, str], sql: str, *, db: str) -> str:
    cmd = [
        "psql",
        f"host={pg['host']}",
        f"port={pg['port']}",
        f"user={pg['user']}",
        f"dbname={db}",
    ]
    if pg.get("sslmode"):
        cmd.append(f"sslmode={pg['sslmode']}")
    cmd += ["-v", "ON_ERROR_STOP=1", "-Atc", sql]
    result = subprocess.run(cmd, env=psql_env(pg), check=False, capture_output=True)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or b"").replace(pg["password"].encode(), b"***")
        raise RuntimeError(f"deep fingerprint query failed rc={result.returncode}: {detail[:300]!r}")
    return hashlib.sha256(result.stdout).hexdigest()


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
    meta["table_content_sha256"] = {}
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
        quoted = safe_ident(t)
        meta["table_content_sha256"][t] = query_sha256(
            pg,
            (
                "SELECT encode(convert_to(row_to_json(t)::text,'UTF8'),'base64') "
                f'FROM public."{quoted}" AS t ORDER BY 1'
            ),
            db=db,
        )
    meta["columns"] = sorted(
        x.strip()
        for x in run_psql(
            pg,
            "SELECT row_to_json(x)::text FROM ("
            "SELECT table_name,ordinal_position,column_name,data_type,udt_name,is_nullable,column_default,"
            "is_identity,identity_generation,is_generated,generation_expression "
            "FROM information_schema.columns WHERE table_schema='public' "
            "ORDER BY table_name,ordinal_position) x",
            db=db,
        ).splitlines()
        if x.strip()
    )
    meta["sequences"] = sorted(
        x.strip()
        for x in run_psql(
            pg,
            "SELECT row_to_json(x)::text FROM ("
            "SELECT schemaname,sequencename,start_value,min_value,max_value,increment_by,cycle,cache_size,last_value "
            "FROM pg_sequences WHERE schemaname='public' ORDER BY sequencename) x",
            db=db,
        ).splitlines()
        if x.strip()
    )
    meta["indexes"] = sorted(
        x.strip()
        for x in run_psql(
            pg,
            "SELECT row_to_json(x)::text FROM (SELECT tablename,indexname,indexdef FROM pg_indexes "
            "WHERE schemaname='public' ORDER BY tablename,indexname) x",
            db=db,
        ).splitlines()
        if x.strip()
    )
    meta["constraints"] = sorted(
        x.strip()
        for x in run_psql(
            pg,
            "SELECT row_to_json(x)::text FROM (SELECT c.conrelid::regclass::text AS table_name,c.conname,"
            "pg_get_constraintdef(c.oid,true) AS definition FROM pg_constraint c "
            "JOIN pg_namespace n ON n.oid=c.connamespace WHERE n.nspname='public' "
            "ORDER BY c.conrelid::regclass::text,c.conname) x",
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
        if (src.get("table_content_sha256") or {}).get(t) != (dst.get("table_content_sha256") or {}).get(t):
            errs.append(f"row_content_digest {t}: mismatch")
    for label, key in (
        ("columns", "columns"),
        ("sequences", "sequences"),
        ("indexes", "indexes"),
        ("constraints", "constraints"),
    ):
        s_set = set(src.get(key) or [])
        d_set = set(dst.get(key) or [])
        if s_set != d_set:
            errs.append(f"{label} mismatch missing_count={len(s_set - d_set)} extra_count={len(d_set - s_set)}")
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

print("[managed-pg-restore] mode=read-only-verify")
print(f"[managed-pg-restore] managed={redact_dsn(managed_raw)}")
print(f"[managed-pg-restore] source={redact_dsn(source_raw)}")
print(f"[managed-pg-restore] dump={DUMP}")

if not DUMP.is_file():
    raise SystemExit(f"dump missing: {DUMP}")
actual_dump_sha256 = file_sha256(DUMP)
if not re.fullmatch(r"[0-9a-f]{64}", EXPECTED_DUMP_SHA256) or not hmac.compare_digest(
    actual_dump_sha256,
    EXPECTED_DUMP_SHA256,
):
    raise SystemExit("immutable dump SHA-256 does not match the approved digest")
listing = subprocess.run(
    ["pg_restore", "--list", str(DUMP)],
    check=False,
    capture_output=True,
    text=True,
)
if listing.returncode != 0 or not any(line and not line.startswith(";") for line in listing.stdout.splitlines()):
    raise SystemExit("custom-format dump inventory is invalid")
print(f"[managed-pg-restore] dump_sha256={actual_dump_sha256} inventory=valid")

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
    raise SystemExit("isolated restored target database is missing; this read-only verifier never creates it")

source_endpoint = (source_pg["host"].lower(), source_pg["port"], SOURCE_DB)
target_endpoint = (managed_pg["host"].lower(), managed_pg["port"], TARGET_DB)
if source_endpoint == target_endpoint:
    raise SystemExit("source and restored target resolve to the same configured database")
source_identity = run_psql(
    source_pg,
    "SELECT COALESCE(inet_server_addr()::text,'local') || ':' || inet_server_port()::text || '/' || current_database()",
    db=SOURCE_DB,
)
target_identity = run_psql(
    managed_pg,
    "SELECT COALESCE(inet_server_addr()::text,'local') || ':' || inet_server_port()::text || '/' || current_database()",
    db=TARGET_DB,
)
if source_identity == target_identity:
    raise SystemExit("source and restored target are the same live PostgreSQL database")
print("[managed-pg-restore] source_target_identity=distinct")

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
print(
    "[managed-pg-restore] BLOCKED: source/target currently match, but this legacy helper cannot authenticate "
    "that the target was created from the supplied dump; it is not a restore acceptance gate",
    file=sys.stderr,
)
raise SystemExit(3)
PY
}

if [[ -n "$REMOTE" ]]; then
  case "$REMOTE" in
    node01) REMOTE_HOST="$NODE01_HOST" ;;
    *) echo "unsupported --remote value: $REMOTE (use node01)" >&2; exit 2 ;;
  esac
  echo "[managed-pg-restore] remote=${REMOTE_HOST}"
  REMOTE_SCRIPT="/opt/linasbot/scripts/ha/managed_pg_restore_verify.sh"
  REMOTE_ARGS=(
    "$ENV_FILE"
    --expected-dump-sha256 "$EXPECTED_DUMP_SHA256"
    --dump "$DUMP_PATH"
    --source-env "$SOURCE_ENV"
  )
  if ssh -o BatchMode=yes "root@${REMOTE_HOST}" "test -x '${REMOTE_SCRIPT}'"; then
    ssh -o BatchMode=yes "root@${REMOTE_HOST}" "bash '${REMOTE_SCRIPT}' $(printf '%q ' "${REMOTE_ARGS[@]}")"
  else
    echo "[managed-pg-restore] remote script missing at ${REMOTE_SCRIPT}; run from repo checkout on node01" >&2
    exit 1
  fi
else
  run_body "$ENV_FILE" "$DUMP_PATH" "$SOURCE_ENV"
fi

echo "[managed-pg-restore] DONE mode=read-only-diagnostic-not-acceptance"
