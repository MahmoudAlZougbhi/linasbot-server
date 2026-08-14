"""META_REGISTRY_BACKEND resolver (LOC split from bindings)."""

from __future__ import annotations

import os
from typing import Literal, cast

from services.meta_app_registry_common import MetaRegistryError

MetaRegistryBackend = Literal["file", "postgres", "dual"]


def resolve_meta_registry_backend() -> MetaRegistryBackend:
    """Resolve meta registry backend.

    Production-cutover-ready default is ``postgres``. Explicit options:
      - ``file`` — local/dev or emergency rollback
      - ``postgres`` — Postgres SoT only (fail closed; no file fallback)
      - ``dual`` — migration helper only (PG primary + file mirror)
    """
    raw = (os.getenv("META_REGISTRY_BACKEND") or "postgres").strip().lower()
    if raw not in {"file", "postgres", "dual"}:
        raise MetaRegistryError("META_REGISTRY_BACKEND must be file|postgres|dual")
    return cast(MetaRegistryBackend, raw)
