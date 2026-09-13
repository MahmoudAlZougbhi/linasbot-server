"""Publish isolated live-test tenants through the real CM version/pointer store."""

from __future__ import annotations

import time
from typing import Any

from services.cm.atomic_io import compute_checksum
from services.cm.constants import CM_SECTIONS
from services.cm.paths import ensure_cm_dirs
from services.cm.schemas import PublishedPointer, default_section_payload, utc_now
from services.cm.version_store import write_published_pointer, write_version_content
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
from services.customer_ai.providers.spaces import KNOWLEDGE_MODEL


def _full_sections(overlay: dict[str, Any]) -> dict[str, Any]:
    out = {name: default_section_payload(name) for name in CM_SECTIONS}
    for key, payload in overlay.items():
        out[key] = payload
    return out


def linas_merged_sections() -> dict[str, Any]:
    from services.cm.version_store import load_published_content

    _pointer, raw = load_published_content(TENANT_LINAS)
    sections = {str(key): dict(value) if isinstance(value, dict) else value for key, value in (raw or {}).items()}
    for name in CM_SECTIONS:
        if name not in sections:
            sections[name] = default_section_payload(name)
    sections["branches"] = merge_linas_hours(dict(sections.get("branches") or {}))
    sections["opening_hours"] = merge_linas_opening_hours(dict(sections.get("opening_hours") or {}))
    extras = merge_linas_extras(
        {
            "dynamic_messages": dict(sections.get("dynamic_messages") or {}),
            "knowledge": dict(sections.get("knowledge") or {}),
            "prices": dict(sections.get("prices") or {}),
            "requests_appointments": dict(sections.get("requests_appointments") or {}),
        }
    )
    sections.update(extras)
    return sections


def publish_sections(tenant_id: str, sections: dict[str, Any], *, revision: str) -> dict[str, Any]:
    tid = (tenant_id or "").strip()
    if not tid:
        raise ValueError("tenant_id required")
    ensure_cm_dirs(tid)
    checksums = {key: compute_checksum(payload) for key, payload in sections.items()}
    write_version_content(tid, revision, sections)
    pointer = PublishedPointer(
        content_version_id=revision,
        index_version_id=f"idx_{revision}",
        checksums=checksums,
        embedding_provider="voyage",
        embedding_model=KNOWLEDGE_MODEL,
        embedding_version="live-matrix",
        embedding_dimensions=1024,
        updated_at=utc_now(),
    )
    write_published_pointer(tid, pointer)
    try:
        from services.customer_reply_v2.manifest import clear_manifest_cache

        clear_manifest_cache(tid)
    except Exception:
        pass
    return {
        "tenant_id": tid,
        "revision": revision,
        "sections": sorted(sections.keys()),
        "peer": "skipped",
    }


async def publish_and_index(tenant_id: str, sections: dict[str, Any], *, revision: str) -> dict[str, Any]:
    import asyncio

    from services.customer_ai.search.index_schedule import run_tenant_index_job

    published = publish_sections(tenant_id, sections, revision=revision)
    index: dict[str, Any] = {}
    for attempt in range(5):
        index = await run_tenant_index_job(tenant_id, revision=revision, reason="live-tenant-matrix")
        if index.get("ready"):
            break
        await asyncio.sleep(12 * (attempt + 1))
    return {
        **published,
        "index_ready": bool(index.get("ready")),
        "index_reason": str(index.get("reason") or ""),
        "index_count": index.get("count"),
        "index_attempts": attempt + 1,
    }


async def seed_and_publish_all() -> dict[str, Any]:
    import asyncio

    stamp = str(int(time.time()))
    rows = {
        TENANT_LINAS: await publish_and_index(TENANT_LINAS, linas_merged_sections(), revision=f"live_linas_{stamp}"),
    }
    await asyncio.sleep(8)
    rows[TENANT_TEST] = await publish_and_index(
        TENANT_TEST, _full_sections(test1_sections()), revision=f"live_test1_{stamp}"
    )
    await asyncio.sleep(8)
    rows[TENANT_TEST_2] = await publish_and_index(
        TENANT_TEST_2, _full_sections(test2_sections()), revision=f"live_test2_{stamp}"
    )
    return rows
