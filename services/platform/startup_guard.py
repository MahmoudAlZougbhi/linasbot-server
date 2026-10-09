"""Refuse to boot a staging/production process that is missing shared stores.

The guard runs only when LINAS_REQUIRE_SHARED_STORES=1. Current droplets do not set it.
"""

from __future__ import annotations

import os


class SharedStoreConfigError(RuntimeError):
    pass


def shared_stores_required() -> bool:
    return (os.getenv("LINAS_REQUIRE_SHARED_STORES") or "").strip().lower() in {"1", "true", "yes"}


def assert_shared_stores_configured() -> None:
    if not shared_stores_required():
        return
    missing = []
    if not (os.getenv("LINAS_PLATFORM_DATABASE_URL") or os.getenv("LINAS_WHATSAPP_DATABASE_URL") or "").strip():
        missing.append("postgres")
    if not (os.getenv("REDIS_URL") or os.getenv("LINAS_REDIS_URL") or "").strip():
        missing.append("valkey")
    spaces = ("LINAS_SPACES_KEY", "LINAS_SPACES_SECRET", "LINAS_SPACES_BUCKET")
    if not all((os.getenv(name) or "").strip() for name in spaces):
        missing.append("spaces")
    if missing:
        raise SharedStoreConfigError("missing shared stores: " + ",".join(missing))
