"""Publish isolated live-test tenants through the real CM draft → publish path."""

from __future__ import annotations

from typing import Any

from services.cm.storage import get_draft, put_draft
from services.customer_ai.evals.live_tenant_seed import (
    TENANT_LINAS,
    TENANT_TEST,
    TENANT_TEST_2,
    merge_linas_extras,
    merge_linas_hours,
    merge_linas_opening_hours,
    test1_sections,
    test2_sections,
)

ACTOR = "live-tenant-matrix"


def _put(tenant_id: str, section: str, payload: dict[str, Any]) -> None:
    env = get_draft(section, tenant_id=tenant_id, create_default=True)
    put_draft(
        section,
        payload=payload,
        if_match=env.etag,
        tenant_id=tenant_id,
        updated_by=ACTOR,
        allow_create=True,
    )


def seed_new_tenant(tenant_id: str, sections: dict[str, Any]) -> None:
    for section, payload in sections.items():
        _put(tenant_id, section, payload)


def seed_linas_laser() -> None:
    branches = dict(get_draft("branches", tenant_id=TENANT_LINAS, create_default=True).payload)
    _put(TENANT_LINAS, "branches", merge_linas_hours(branches))
    hours = dict(get_draft("opening_hours", tenant_id=TENANT_LINAS, create_default=True).payload)
    _put(TENANT_LINAS, "opening_hours", merge_linas_opening_hours(hours))
    current = {
        name: dict(get_draft(name, tenant_id=TENANT_LINAS, create_default=True).payload)
        for name in ("dynamic_messages", "knowledge", "prices", "requests_appointments")
    }
    merged = merge_linas_extras(current)
    for name, payload in merged.items():
        _put(TENANT_LINAS, name, payload)


async def publish_and_index(tenant_id: str) -> dict[str, Any]:
    from services.cm.publish import publish_draft
    from services.customer_ai.search.index_schedule import run_tenant_index_job

    published = await publish_draft(tenant_id=tenant_id, published_by=ACTOR, notes="live tenant matrix")
    revision = str(published.content_version_id or "")
    index = await run_tenant_index_job(tenant_id, revision=revision, reason="live-tenant-matrix")
    return {
        "tenant_id": tenant_id,
        "content_version_id": revision,
        "index_ready": bool(index.get("ready")),
        "index_reason": str(index.get("reason") or ""),
        "index_count": index.get("count"),
    }


async def seed_and_publish_all() -> dict[str, Any]:
    seed_linas_laser()
    seed_new_tenant(TENANT_TEST, test1_sections())
    seed_new_tenant(TENANT_TEST_2, test2_sections())
    rows = {}
    for tid in (TENANT_LINAS, TENANT_TEST, TENANT_TEST_2):
        rows[tid] = await publish_and_index(tid)
    return rows
