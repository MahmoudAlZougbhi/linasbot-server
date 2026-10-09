"""Feature flags. Missing flags stay on the old path until a later cutover."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

_DEFAULTS = {
    "cm_store": "disk",
    "livechat_store": "firestore",
    "media_store": "disk",
    "queue_backend": "redis",
    "realtime_backend": "local",
    "webhook_ingest": "legacy",
    "vector_backend": "current",
    "scheduler_mode": "embedded",
}


def flag_value(key: str, *, tenant_id: str = "") -> str:
    """Env override wins. Otherwise the built-in old-path default."""
    env_name = f"LINAS_FLAG_{key.strip().upper()}"
    override = (os.getenv(env_name) or "").strip()
    if override:
        return override
    _ = tenant_id
    return _DEFAULTS.get(key, "")


def flag_uses_postgres(key: str, *, tenant_id: str = "") -> bool:
    return flag_value(key, tenant_id=tenant_id) in {"pg", "postgres", "pgvector"}


def config_source() -> str:
    return (os.getenv("LINAS_CONFIG_SOURCE") or "dotenv").strip().lower()


def flag_record(key: str, value: str, *, updated_by: str, scope: str = "global", scope_id: str = "") -> dict[str, Any]:
    return {
        "flag_key": key,
        "scope": scope,
        "scope_id": scope_id,
        "value": value,
        "updated_by": updated_by,
        "updated_at": datetime.now(UTC).isoformat(),
    }
