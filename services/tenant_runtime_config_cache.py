"""Rebuild node-local CM/comment caches from Postgres authoritative state."""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC
from pathlib import Path
from typing import Any

from services.cm.atomic_io import atomic_write_json
from services.cm.paths import published_pointer_path
from services.cm.schemas import PublishedPointer, SectionDraftEnvelope
from services.cm.version_store import read_published_pointer
from services.tenant_runtime_config_backend import tenant_runtime_config_postgres_required
from services.tenant_runtime_config_service import (
    export_comment_settings_for_cache,
    load_actions_payload,
    postgres_enabled,
)

_runtime_logger = logging.getLogger("uvicorn.error")


def _comment_settings_path(tenant_id: str) -> Path:
    from storage.persistent_storage import _DATA_ROOT

    return Path(_DATA_ROOT) / "meta_comment_settings" / f"{tenant_id}.json"


def write_draft_cache(envelope: SectionDraftEnvelope) -> None:
    from services.cm.storage import draft_section_path

    path = draft_section_path(envelope.tenant_id, envelope.section)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, envelope.model_dump(mode="json"))


def write_comment_settings_cache(tenant_id: str) -> None:
    settings = export_comment_settings_for_cache(tenant_id)
    path = _comment_settings_path(tenant_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"settings": settings}, indent=2, sort_keys=True), encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(path)
    os.chmod(path, 0o600)


def rebuild_tenant_cache(tenant_id: str) -> dict[str, Any]:
    """Write local draft/pointer/actions caches from Postgres. Does not change runtime truth."""

    if not postgres_enabled():
        return {"skipped": True, "reason": "file_backend"}
    rebuilt: dict[str, Any] = {"drafts": 0, "comment_settings": False, "actions_cached": False}
    from db.session import whatsapp_session
    from services.cm.constants import CM_SECTIONS
    from services.tenant_runtime_config_pg_store import get_draft_row, get_published_row

    with whatsapp_session() as session:
        for section in CM_SECTIONS:
            row = get_draft_row(session, tenant_id=tenant_id, section=section)
            if row is None:
                continue
            from datetime import datetime

            envelope = SectionDraftEnvelope(
                tenant_id=row.tenant_id,
                section=row.section,
                revision=row.revision,
                etag=row.etag,
                updated_at=datetime.fromtimestamp(row.updated_at, tz=UTC),
                updated_by=row.updated_by,
                payload=row.payload,
            )
            write_draft_cache(envelope)
            rebuilt["drafts"] += 1
        published = get_published_row(session, tenant_id=tenant_id)
    if published is not None and published.content_version_id:
        pointer_path = published_pointer_path(tenant_id)
        pointer_path.parent.mkdir(parents=True, exist_ok=True)
        pointer = PublishedPointer(
            content_version_id=published.content_version_id,
            index_version_id=published.index_version_id,
            checksums=dict(published.checksums or {}),
            embedding_provider=published.embedding_provider,
            embedding_model=published.embedding_model,
            embedding_dimensions=published.embedding_dimensions,
            embedding_version=published.embedding_version,
            schema_version=published.schema_version,
        )
        atomic_write_json(pointer_path, pointer.model_dump(mode="json"))
        rebuilt["pointer_cached"] = True
    write_comment_settings_cache(tenant_id)
    rebuilt["comment_settings"] = True
    actions = load_actions_payload(tenant_id)
    rebuilt["actions_cached"] = bool(actions)
    _runtime_logger.info("[tenant-runtime-cache] rebuilt tenant=%s summary=%s", tenant_id, rebuilt)
    return rebuilt


def local_cache_digest_mismatch(tenant_id: str) -> bool:
    """True when local published actions disagree with Postgres (rebuildable drift)."""

    if not tenant_runtime_config_postgres_required():
        return False
    actions = load_actions_payload(tenant_id)
    if actions is None:
        return False
    pointer = read_published_pointer(tenant_id)
    if pointer is None:
        return True
    try:
        from services.cm.version_store import load_published_content

        _ptr, sections = load_published_content(tenant_id)
        local_actions = sections.get("actions") or {}
    except Exception:
        return True
    return dict(local_actions) != actions
