"""High-level tenant runtime config API (Postgres SoT + optional file cache)."""

from __future__ import annotations

import logging
from datetime import UTC
from typing import Any

from db.session import whatsapp_session
from services.cm.schemas import SectionDraftEnvelope
from services.tenant_runtime_config_backend import (
    require_tenant_runtime_config_postgres,
    tenant_runtime_config_postgres_required,
)
from services.tenant_runtime_config_pg_store import (
    RevisionConflictError,
    get_comment_asset_row,
    get_draft_row,
    get_published_row,
    get_sync_cursor,
    list_comment_asset_rows,
    migration_applied,
    record_migration,
    upsert_comment_asset_row,
    upsert_draft_row,
    upsert_published_row,
    upsert_sync_cursor,
)

_runtime_logger = logging.getLogger("uvicorn.error")
MIGRATION_ID_V1 = "tenant_runtime_config_v1"


class TenantRuntimeConfigConflictError(Exception):
    code = "CONFLICT"


def postgres_enabled() -> bool:
    return tenant_runtime_config_postgres_required()


def shared_revision_for_tenant(tenant_id: str) -> dict[str, Any]:
    """Return published + draft revisions for readiness proof."""

    if not postgres_enabled():
        return {"backend": "file", "reachable": True}
    require_tenant_runtime_config_postgres()
    with whatsapp_session() as session:
        published = get_published_row(session, tenant_id=tenant_id)
        drafts = {
            row.section: row.revision
            for row in [
                get_draft_row(session, tenant_id=tenant_id, section=section) for section in ("actions", "comments")
            ]
            if row is not None
        }
        migrated = migration_applied(session, tenant_id=tenant_id, migration_id=MIGRATION_ID_V1)
    return {
        "backend": "postgres",
        "reachable": True,
        "migration_applied": migrated,
        "published_revision": int(published.revision) if published else 0,
        "content_version_id": published.content_version_id if published else "",
        "draft_revisions": drafts,
    }


def load_actions_payload(tenant_id: str) -> dict[str, Any] | None:
    if not postgres_enabled():
        return None
    require_tenant_runtime_config_postgres()
    with whatsapp_session() as session:
        published = get_published_row(session, tenant_id=tenant_id)
        if published is None or not published.actions_payload:
            return None
        return dict(published.actions_payload)


def save_actions_payload(
    *,
    tenant_id: str,
    actions_payload: dict[str, Any],
    expected_published_revision: int | None,
    published_meta: dict[str, Any],
) -> int:
    require_tenant_runtime_config_postgres()
    with whatsapp_session() as session:
        current = get_published_row(session, tenant_id=tenant_id)
        next_revision = (int(current.revision) + 1) if current else 1
        upsert_published_row(
            session,
            tenant_id=tenant_id,
            expected_revision=expected_published_revision if current else -1,
            revision=next_revision,
            content_version_id=str(
                published_meta.get("content_version_id") or (current.content_version_id if current else "")
            ),
            index_version_id=str(
                published_meta.get("index_version_id") or (current.index_version_id if current else "")
            ),
            checksums=dict(published_meta.get("checksums") or (current.checksums if current else {})),
            actions_payload=actions_payload,
            embedding_provider=str(
                published_meta.get("embedding_provider") or (current.embedding_provider if current else "")
            ),
            embedding_model=str(published_meta.get("embedding_model") or (current.embedding_model if current else "")),
            embedding_dimensions=int(
                published_meta.get("embedding_dimensions") or (current.embedding_dimensions if current else 0)
            ),
            embedding_version=str(
                published_meta.get("embedding_version") or (current.embedding_version if current else "")
            ),
            schema_version=int(published_meta.get("schema_version") or (current.schema_version if current else 1)),
            published_at=float(published_meta.get("published_at") or (current.published_at if current else 0)),
        )
        return next_revision


def load_draft_envelope(tenant_id: str, section: str) -> SectionDraftEnvelope | None:
    if not postgres_enabled():
        return None
    require_tenant_runtime_config_postgres()
    with whatsapp_session() as session:
        row = get_draft_row(session, tenant_id=tenant_id, section=section)
        if row is None:
            return None
        from datetime import datetime

        return SectionDraftEnvelope(
            tenant_id=row.tenant_id,
            section=row.section,
            revision=row.revision,
            etag=row.etag,
            updated_at=datetime.fromtimestamp(row.updated_at, tz=UTC),
            updated_by=row.updated_by,
            payload=row.payload,
        )


def save_draft_envelope(
    *,
    envelope: SectionDraftEnvelope,
    expected_revision: int | None,
) -> SectionDraftEnvelope:
    require_tenant_runtime_config_postgres()
    with whatsapp_session() as session:
        try:
            upsert_draft_row(
                session,
                tenant_id=envelope.tenant_id,
                section=envelope.section,
                expected_revision=expected_revision,
                revision=envelope.revision,
                etag=envelope.etag,
                payload=dict(envelope.payload or {}),
                updated_by=envelope.updated_by,
            )
        except RevisionConflictError as exc:
            raise TenantRuntimeConfigConflictError(str(exc)) from exc
    from services.tenant_runtime_config_cache import write_draft_cache

    write_draft_cache(envelope)
    return envelope


def load_comment_asset_setting(
    *,
    tenant_id: str,
    asset_key: str,
) -> dict[str, Any] | None:
    if not postgres_enabled():
        return None
    require_tenant_runtime_config_postgres()
    with whatsapp_session() as session:
        row = get_comment_asset_row(session, tenant_id=tenant_id, asset_key=asset_key)
        if row is None:
            return None
        return {
            "enabled": row.enabled,
            "instructions": row.instructions,
            "revision": row.revision,
            "updated_at": row.updated_at,
        }


def save_comment_asset_setting(
    *,
    tenant_id: str,
    asset_key: str,
    app_key: str,
    channel: str,
    asset_id: str,
    enabled: bool,
    instructions: str,
    expected_revision: int | None,
) -> dict[str, Any]:
    require_tenant_runtime_config_postgres()
    with whatsapp_session() as session:
        current = get_comment_asset_row(session, tenant_id=tenant_id, asset_key=asset_key)
        next_revision = (int(current.revision) + 1) if current else 1
        try:
            row = upsert_comment_asset_row(
                session,
                tenant_id=tenant_id,
                asset_key=asset_key,
                app_key=app_key,
                channel=channel,
                asset_id=asset_id,
                enabled=enabled,
                instructions=instructions,
                expected_revision=expected_revision if current else -1,
                revision=next_revision,
            )
        except RevisionConflictError as exc:
            raise TenantRuntimeConfigConflictError(str(exc)) from exc
    from services.tenant_runtime_config_cache import write_comment_settings_cache

    write_comment_settings_cache(tenant_id)
    return {
        "enabled": row.enabled,
        "instructions": row.instructions,
        "revision": row.revision,
        "updated_at": row.updated_at,
    }


def load_sync_cursor(*, binding_id: str, cursor_key: str) -> str | None:
    if not postgres_enabled():
        return None
    with whatsapp_session() as session:
        return get_sync_cursor(session, binding_id=binding_id, cursor_key=cursor_key)


def save_sync_cursor(
    *,
    binding_id: str,
    cursor_key: str,
    cursor_value: str,
    expected_revision: int | None,
) -> int:
    require_tenant_runtime_config_postgres()
    with whatsapp_session() as session:
        from services.tenant_runtime_config_pg_store import MetaCommentSyncCursorRow

        row = session.get(
            MetaCommentSyncCursorRow,
            {"binding_id": binding_id, "cursor_key": cursor_key},
        )
        next_revision = (int(row.revision) + 1) if row else 1
        upsert_sync_cursor(
            session,
            binding_id=binding_id,
            cursor_key=cursor_key,
            cursor_value=cursor_value,
            expected_revision=expected_revision if row else -1,
            revision=next_revision,
        )
        return next_revision


def mark_migration_applied(*, tenant_id: str, audit: dict[str, Any]) -> None:
    with whatsapp_session() as session:
        record_migration(session, tenant_id=tenant_id, migration_id=MIGRATION_ID_V1, audit=audit)


def migration_is_applied(*, tenant_id: str) -> bool:
    if not postgres_enabled():
        return False
    with whatsapp_session() as session:
        return migration_applied(session, tenant_id=tenant_id, migration_id=MIGRATION_ID_V1)


def export_comment_settings_for_cache(tenant_id: str) -> dict[str, dict[str, Any]]:
    if not postgres_enabled():
        return {}
    with whatsapp_session() as session:
        rows = list_comment_asset_rows(session, tenant_id=tenant_id)
    settings: dict[str, dict[str, Any]] = {}
    for row in rows:
        settings[row.asset_key] = {
            "enabled": row.enabled,
            "instructions": row.instructions,
            "updated_at": row.updated_at,
        }
    return settings
