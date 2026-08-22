"""Periodic HA tenant-config repair sync (CM + integration settings)."""

from __future__ import annotations

from services.cm.constants import DEFAULT_TENANT_ID
from services.durable_event_claim import release_job_lock, try_acquire_job_lock
from services.ha_tenant_config_peer_sync import reconcile_tenant_config_with_peer


async def run_ha_tenant_config_peer_sync_job() -> None:
    if not try_acquire_job_lock("ha_tenant_config_peer_sync_tick", ttl_seconds=110):
        return
    try:
        reconcile_tenant_config_with_peer(DEFAULT_TENANT_ID)
    finally:
        release_job_lock("ha_tenant_config_peer_sync_tick")
