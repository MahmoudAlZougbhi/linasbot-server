#!/usr/bin/env bash
# Read-only WhatsApp Postgres reachability probe for production.
# Never prints passwords or full DSNs. Safe for CI logs.
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$APP_DIR"

echo "[wa-db-probe] deployed_sha=$(git rev-parse HEAD 2>/dev/null || echo unknown)"

python3 - <<'PY'
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from urllib.parse import urlparse


def load_env(path: str) -> dict[str, str]:
    p = Path(path)
    if not p.exists():
        print(f"[wa-db-probe] env_file path={path} exists=false")
        return {}
    out: dict[str, str] = {}
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        out[k.strip()] = v.strip().strip("'").strip('"')
    print(f"[wa-db-probe] env_file path={path} exists=true")
    return out


merged: dict[str, str] = {}
for path in (
    "/opt/linasbot/.env",
    str(Path(os.environ.get("APP_DIR", "/opt/linasbot")) / ".env"),
    "/opt/linasbot/linaslaserbot-2.7.22/.env",
):
    for k, v in load_env(path).items():
        merged.setdefault(k, v)

keys = [
    "LINAS_WHATSAPP_DATABASE_URL",
    "DATABASE_URL",
    "POSTGRES_HOST",
    "POSTGRES_DB",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "WHATSAPP_CLOUD_PUBLIC_AVAILABILITY",
    "WHATSAPP_CLOUD_CONNECTION_UI_ENABLED",
    "WHATSAPP_CLOUD_REQUIRE_PILOT_ENTITLEMENT",
    "CM_DISABLE_LINAS_LEGACY_BRIDGE",
    "LINAS_REQUIRE_REDIS",
    "LINASBOT_TENANT_ID",
    "SUBSCRIPTION_EXEMPT_TENANT_IDS",
    "META_WHATSAPP_EMBEDDED_SIGNUP_CONFIG_ID",
    "META_CREDENTIAL_ENCRYPTION_KEY",
    "PUBLIC_URL",
]
print("[wa-db-probe] --- presence ---")
for k in keys:
    v = merged.get(k, "")
    print(f"[wa-db-probe] {k}: present={bool(v)} len={len(v)}")


def sanitize(name: str, raw: str) -> None:
    if not raw:
        print(f"[wa-db-probe] {name}: unset")
        return
    scheme = raw.split(":", 1)[0]
    parse_url = raw
    if parse_url.startswith("postgresql+psycopg2://"):
        parse_url = "postgresql://" + parse_url[len("postgresql+psycopg2://") :]
    u = urlparse(parse_url)
    print(
        f"[wa-db-probe] {name}: scheme={scheme} host={u.hostname!r} port={u.port} "
        f"dbname={(u.path or '/').lstrip('/')!r} user_set={bool(u.username)} "
        f"password_set={bool(u.password)}"
    )


print("[wa-db-probe] --- db sanitize ---")
sanitize("LINAS_WHATSAPP_DATABASE_URL", merged.get("LINAS_WHATSAPP_DATABASE_URL", ""))
sanitize("DATABASE_URL", merged.get("DATABASE_URL", ""))


def run(cmd: str) -> str:
    try:
        completed = subprocess.run(
            cmd,
            shell=True,
            check=False,
            capture_output=True,
            text=True,
            timeout=25,
        )
        out = (completed.stdout or "").strip()
        err = (completed.stderr or "").strip()
        if out and err:
            return f"{out}\n{err}"
        return out or err or f"exit={completed.returncode}"
    except Exception as exc:  # noqa: BLE001
        return f"err={type(exc).__name__}"


print("[wa-db-probe] --- infra ---")
checks = {
    "linasbot_active": "systemctl is-active linasbot || true",
    "docker_ps": "docker ps --format '{{.Names}}|{{.Image}}|{{.Status}}' 2>/dev/null | head -40 || echo no_docker",
    "listen_5432": "ss -lntp 2>/dev/null | grep -E ':5432\\b' || echo no_listen_5432",
    "getent_postgres": "getent hosts postgres || echo getent_postgres_fail",
    "pg_units": "systemctl list-units --type=service --all 'postgresql*' --no-legend 2>/dev/null | head -15 || echo no_pg_units",
    "pg_packages": "dpkg -l 'postgresql*' 2>/dev/null | awk '/^ii/{print $2,$3}' | head -15 || echo no_pg_pkg",
    "compose_notes": "rg -n 'postgres|DATABASE|Redis/Postgres' /opt/linasbot/docker-compose*.yml 2>/dev/null | head -40 || true",
    "pg_isready_local": "command -v pg_isready >/dev/null && pg_isready -h 127.0.0.1 -p 5432 2>&1 || echo pg_isready_missing_or_fail",
    "pg_isready_postgres_host": "command -v pg_isready >/dev/null && pg_isready -h postgres -p 5432 2>&1 || echo pg_isready_postgres_host_fail",
}
for name, cmd in checks.items():
    print(f"[wa-db-probe] [{name}]")
    print(run(cmd))

# Attempt SQLAlchemy SELECT 1 without printing DSN.
url = (merged.get("LINAS_WHATSAPP_DATABASE_URL") or merged.get("DATABASE_URL") or "").strip()
print("[wa-db-probe] --- connectivity ---")
if not url:
    print("[wa-db-probe] connect=skipped reason=url_unset")
else:
    os.environ["LINAS_WHATSAPP_DATABASE_URL"] = url
    try:
        from sqlalchemy import create_engine, text

        engine = create_engine(url, pool_pre_ping=True, future=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("[wa-db-probe] connect=ok")
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        # Redact any accidental credential fragments.
        msg = msg.replace(url, "<DSN_REDACTED>")
        if "@" in msg:
            msg = msg.split("(", 1)[0].strip() or type(exc).__name__
        print(f"[wa-db-probe] connect=fail type={type(exc).__name__} detail={msg[:240]}")

print("[wa-db-probe] COMPLETE_OK")
PY
