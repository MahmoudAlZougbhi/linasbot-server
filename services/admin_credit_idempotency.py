"""Admin credit idempotency store (file or Postgres via LINAS_BILLING_BACKEND)."""

from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path
from typing import Any

from services.billing_backend import billing_uses_postgres, require_billing_pg_session
from storage.persistent_storage import _DATA_ROOT

_LOCK = threading.RLock()
_IDEMP_DIR = Path(_DATA_ROOT) / "billing" / "admin_credit_idempotency"


def _idempotency_path(key: str) -> Path:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:40]
    return _IDEMP_DIR / f"{digest}.json"


def load_admin_credit_idempotent(key: str) -> dict[str, Any] | None:
    if billing_uses_postgres():
        from services.billing_pg_store import admin_credit_load

        with require_billing_pg_session() as session:
            return admin_credit_load(session, key)

    path = _idempotency_path(key)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def store_admin_credit_idempotent(key: str, payload: dict[str, Any]) -> None:
    if billing_uses_postgres():
        from services.billing_pg_store import admin_credit_store

        with require_billing_pg_session() as session:
            admin_credit_store(session, key, payload)
        return

    _IDEMP_DIR.mkdir(parents=True, exist_ok=True)
    path = _idempotency_path(key)
    with _LOCK:
        path.write_text(
            json.dumps({"idempotency_key": key, "ts": time.time(), "response": payload}),
            encoding="utf-8",
        )
