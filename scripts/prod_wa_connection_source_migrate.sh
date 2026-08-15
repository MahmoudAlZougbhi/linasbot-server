#!/usr/bin/env bash
# Preflight/apply the additive WhatsApp connection_source migration from the
# exact deployed release. The guarded runner owns the global production lock.
set -euo pipefail

# shellcheck source=scripts/ha/require_production_mutation_guard.sh
source /opt/linasbot/scripts/ha/require_production_mutation_guard.sh
linas_require_production_mutation_guard "scripts/prod_wa_connection_source_migrate.sh"

PHASE="${PHASE:-}"
CONFIRM="${CONFIRM:-}"
if [ "$PHASE" != "PREFLIGHT_ONLY" ] && [ "$PHASE" != "MIGRATE_APPLY" ]; then
  echo "[wa-src] BLOCKED: phase is invalid" >&2
  exit 2
fi
if [ "$PHASE" = "MIGRATE_APPLY" ] && [ "$CONFIRM" != "APPLY_WA_CONNECTION_SOURCE_MIGRATION" ]; then
  echo "[wa-src] BLOCKED: confirmation mismatch" >&2
  exit 2
fi

export PHASE
cd /opt/linasbot
/opt/linasbot/venv/bin/python - <<'PY'
from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

from dotenv import dotenv_values
from sqlalchemy import create_engine, inspect, text

ENV_PATH = Path("/opt/linasbot/.env")
SNAPSHOT_ROOT = Path("/opt/linasbot_backups/wa_schema")
TARGET = "20260811_wa_app_review_source"
ALLOWED_PREVIOUS = {None, "20260811_whatsapp_smart_followup", TARGET}


def load_canonical_environment() -> dict[str, str]:
    parsed = dotenv_values(ENV_PATH, interpolate=False)
    values = {str(key): "" if value is None else str(value) for key, value in parsed.items()}
    for key in (
        "DATABASE_URL",
        "LINAS_WHATSAPP_DATABASE_URL",
        "LINAS_WHATSAPP_ALLOW_SQLITE",
        "WHATSAPP_CLOUD_PUBLIC_AVAILABILITY",
        "META_WHATSAPP_APP_REVIEW_BIND_TOKEN",
    ):
        os.environ.pop(key, None)
        if key in values:
            os.environ[key] = values[key]
    return values


def inventory(engine) -> tuple[dict[str, object], list[dict[str, object]]]:
    with engine.connect() as connection:
        current = connection.execute(text("select version_num from alembic_version")).scalar()
        columns = [dict(row) for row in inspect(engine).get_columns("whatsapp_connections")]
        names = {str(row["name"]) for row in columns}
        result: dict[str, object] = {
            "alembic_current": current,
            "has_connection_source": "connection_source" in names,
            "connections": connection.execute(text("select count(*) from whatsapp_connections")).scalar(),
            "credentials": connection.execute(text("select count(*) from whatsapp_credentials")).scalar(),
            "active": connection.execute(
                text(
                    """
                    select count(*) from whatsapp_connections
                    where lifecycle_status in
                      ('connected','provisioning','syncing_history','needs_attention','starting','awaiting_meta')
                    """
                )
            ).scalar(),
        }
        if result["has_connection_source"]:
            result["meta_app_review_test"] = connection.execute(
                text("select count(*) from whatsapp_connections where connection_source='meta_app_review_test'")
            ).scalar()
            result["unexpected_sources"] = connection.execute(
                text(
                    "select count(*) from whatsapp_connections "
                    "where connection_source not in ('embedded_signup','meta_app_review_test')"
                )
            ).scalar()
        return result, columns


def write_snapshot(payload: dict[str, object], columns: list[dict[str, object]]) -> tuple[Path, Path]:
    SNAPSHOT_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(SNAPSHOT_ROOT, 0o700)
    if SNAPSHOT_ROOT.is_symlink() or stat.S_IMODE(SNAPSHOT_ROOT.stat().st_mode) != 0o700:
        raise RuntimeError("WhatsApp schema snapshot directory is insecure")
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    before = SNAPSHOT_ROOT / f"pre_connection_source_{stamp}.json"
    shape = SNAPSHOT_ROOT / f"pre_connection_source_{stamp}_columns.json"
    for path, body in (
        (before, payload),
        (shape, columns),
    ):
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(body, handle, indent=2, sort_keys=True, default=str)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
    return before, shape


values = load_canonical_environment()
public = str(values.get("WHATSAPP_CLOUD_PUBLIC_AVAILABILITY") or "").strip().lower()
if public not in {"", "false", "0", "no", "off"}:
    raise RuntimeError("WhatsApp public availability must remain disabled")
if str(values.get("META_WHATSAPP_APP_REVIEW_BIND_TOKEN") or "").strip():
    raise RuntimeError("WhatsApp App Review bind token must be absent")

url = str(values.get("LINAS_WHATSAPP_DATABASE_URL") or values.get("DATABASE_URL") or "").strip()
parsed = urlparse(url.replace("postgresql+psycopg2://", "postgresql://"))
if parsed.scheme not in {"postgresql", "postgres"} or not parsed.hostname:
    raise RuntimeError("Canonical WhatsApp database authority must be PostgreSQL")
if str(values.get("LINAS_WHATSAPP_ALLOW_SQLITE") or "").strip().lower() == "true":
    raise RuntimeError("SQLite is forbidden for the production WhatsApp migration")

engine = create_engine(url, future=True)
try:
    before, columns = inventory(engine)
    if before["alembic_current"] not in ALLOWED_PREVIOUS:
        raise RuntimeError("WhatsApp database revision is outside the reviewed migration path")
    snapshot, shape = write_snapshot(before, columns)
    print(
        "[wa-src] preflight_ok=true "
        f"connections={before['connections']} credentials={before['credentials']} "
        f"column_present={before['has_connection_source']}"
    )
    print(f"[wa-src] snapshot={snapshot} columns_snapshot={shape}")
    if os.environ["PHASE"] == "PREFLIGHT_ONLY":
        print("[wa-src] PREFLIGHT_COMPLETE")
        raise SystemExit(0)

    if before["alembic_current"] != TARGET:
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", TARGET],
            cwd="/opt/linasbot",
            env=dict(os.environ),
            check=True,
        )
    after, _ = inventory(engine)
    if after["alembic_current"] != TARGET or not after["has_connection_source"]:
        raise RuntimeError("WhatsApp migration target was not installed")
    if after["connections"] != before["connections"] or after["credentials"] != before["credentials"]:
        raise RuntimeError("WhatsApp migration changed owner or credential counts")
    if int(after.get("meta_app_review_test") or 0) != 0 or int(after.get("unexpected_sources") or 0) != 0:
        raise RuntimeError("WhatsApp migration introduced an unexpected connection source")
    print("[wa-src] MIGRATE_COMPLETE_OK")
finally:
    engine.dispose()
PY
