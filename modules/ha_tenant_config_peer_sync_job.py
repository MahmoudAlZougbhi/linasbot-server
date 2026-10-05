"""Periodic HA tenant-config cache rebuild from Postgres SoT."""

from __future__ import annotations

from services.ai_setup.constants import DEFAULT_TENANT_ID
from services.scale.ha_tenant_config_peer_sync import run_tenant_config_cache_rebuild
from services.scale.job_interval_lock import job_interval_lock


async def run_ha_tenant_config_peer_sync_job() -> None:
    with job_interval_lock("ha_tenant_config_peer_sync_tick", ttl_seconds=110) as acquired:
        if not acquired:
            return
        if not (DEFAULT_TENANT_ID or "").strip():
            return
        run_tenant_config_cache_rebuild(tenant_id=DEFAULT_TENANT_ID)
