"""Rebuild node-local CM/comment caches from Postgres (no authoritative rsync)."""

from __future__ import annotations

import logging
from typing import Any

from services.cm.constants import DEFAULT_TENANT_ID
from services.cm.version_store import read_published_pointer
from services.ha_cm_peer_replicate import ha_cm_peer_replicate_enabled, replicate_published_cm_to_peer
from services.tenant_runtime_config_backend import tenant_runtime_config_postgres_required
from services.tenant_runtime_config_cache import rebuild_tenant_cache

_runtime_logger = logging.getLogger("uvicorn.error")


def ha_tenant_config_cache_sync_enabled() -> bool:
    return tenant_runtime_config_postgres_required() and ha_cm_peer_replicate_enabled()


def run_tenant_config_cache_rebuild(*, tenant_id: str | None = None) -> dict[str, Any]:
    """Rebuild local caches from Postgres. Optionally warm immutable CM version dirs to peer."""

    tid = (tenant_id or DEFAULT_TENANT_ID).strip() or DEFAULT_TENANT_ID
    if not tenant_runtime_config_postgres_required():
        return {"skipped": True, "reason": "file_backend"}
    summary = rebuild_tenant_cache(tid)
    pointer = read_published_pointer(tid)
    if pointer is not None and ha_cm_peer_replicate_enabled():
        try:
            replicate_published_cm_to_peer(tenant_id=tid, pointer=pointer)
            summary["version_cache_warmed"] = True
        except Exception:
            _runtime_logger.warning(
                "[tenant-runtime-cache] version_cache_warm_failed tenant=%s",
                tid,
                exc_info=True,
            )
            summary["version_cache_warmed"] = False
    return summary


# Backward-compatible aliases (cache warm only; never authoritative).
def replicate_published_cm_to_peer_if_enabled(tenant_id: str) -> None:
    run_tenant_config_cache_rebuild(tenant_id=tenant_id)


def replicate_cm_draft_to_peer(tenant_id: str) -> None:
    run_tenant_config_cache_rebuild(tenant_id=tenant_id)


def replicate_comment_settings_to_peer(tenant_id: str) -> None:
    run_tenant_config_cache_rebuild(tenant_id=tenant_id)
