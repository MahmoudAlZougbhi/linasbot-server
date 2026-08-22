"""Periodic HA tenant-config cache rebuild from Postgres SoT."""

from __future__ import annotations

from services.cm.constants import DEFAULT_TENANT_ID
from services.durable_event_claim import release_job_lock, try_acquire_job_lock
from services.ha_tenant_config_peer_sync import run_tenant_config_cache_rebuild


async def run_ha_tenant_config_peer_sync_job() -> None:
    if not try_acquire_job_lock("ha_tenant_config_peer_sync_tick", ttl_seconds=110):
        return
    try:
        run_tenant_config_cache_rebuild(tenant_id=DEFAULT_TENANT_ID)
    finally:
        release_job_lock("ha_tenant_config_peer_sync_tick")
