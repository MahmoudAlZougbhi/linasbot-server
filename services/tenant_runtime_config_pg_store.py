"""Low-level Postgres store for tenant runtime configuration with revision CAS."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from db.models.tenant_runtime_config import (
    MetaCommentSyncCursorRow,
    TenantCmDraftSectionRow,
    TenantCmPublishedStateRow,
    TenantMetaCommentAssetSettingRow,
    TenantRuntimeConfigMigrationRow,
)


class RevisionConflictError(Exception):
    code = "REVISION_CONFLICT"

    def __init__(self, *, expected: int, actual: int | None = None) -> None:
        super().__init__(f"revision conflict expected={expected} actual={actual}")
        self.expected = expected
        self.actual = actual


@dataclass(frozen=True)
class DraftRow:
    tenant_id: str
    section: str
    revision: int
    etag: str
    payload: dict[str, Any]
    updated_by: str
    updated_at: float


@dataclass(frozen=True)
class PublishedRow:
    tenant_id: str
    content_version_id: str
    index_version_id: str
    checksums: dict[str, Any]
    actions_payload: dict[str, Any]
    embedding_provider: str
    embedding_model: str
    embedding_dimensions: int
    embedding_version: str
    schema_version: int
    revision: int
    published_at: float
    updated_at: float


@dataclass(frozen=True)
class CommentAssetRow:
    tenant_id: str
    asset_key: str
    app_key: str
    channel: str
    asset_id: str
    enabled: bool
    instructions: str
    revision: int
    updated_at: float


def _draft_from_row(row: TenantCmDraftSectionRow) -> DraftRow:
    return DraftRow(
        tenant_id=row.tenant_id,
        section=row.section,
        revision=int(row.revision or 0),
        etag=str(row.etag or ""),
        payload=dict(row.payload or {}),
        updated_by=str(row.updated_by or ""),
        updated_at=float(row.updated_at or 0),
    )


def _published_from_row(row: TenantCmPublishedStateRow) -> PublishedRow:
    return PublishedRow(
        tenant_id=row.tenant_id,
        content_version_id=str(row.content_version_id or ""),
        index_version_id=str(row.index_version_id or ""),
        checksums=dict(row.checksums or {}),
        actions_payload=dict(row.actions_payload or {}),
        embedding_provider=str(row.embedding_provider or ""),
        embedding_model=str(row.embedding_model or ""),
        embedding_dimensions=int(row.embedding_dimensions or 0),
        embedding_version=str(row.embedding_version or ""),
        schema_version=int(row.schema_version or 1),
        revision=int(row.revision or 0),
        published_at=float(row.published_at or 0),
        updated_at=float(row.updated_at or 0),
    )


def get_draft_row(session: Session, *, tenant_id: str, section: str) -> DraftRow | None:
    row = session.get(TenantCmDraftSectionRow, {"tenant_id": tenant_id, "section": section})
    return _draft_from_row(row) if row is not None else None


def upsert_draft_row(
    session: Session,
    *,
    tenant_id: str,
    section: str,
    expected_revision: int | None,
    revision: int,
    etag: str,
    payload: dict[str, Any],
    updated_by: str,
) -> DraftRow:
    row = session.get(TenantCmDraftSectionRow, {"tenant_id": tenant_id, "section": section})
    now = time.time()
    if row is None:
        if expected_revision not in {None, -1, 0} and expected_revision != -1:
            raise RevisionConflictError(expected=expected_revision or 0, actual=None)
        row = TenantCmDraftSectionRow(
            tenant_id=tenant_id,
            section=section,
            revision=revision,
            etag=etag,
            payload=payload,
            updated_by=updated_by,
            updated_at=now,
        )
        session.add(row)
    else:
        current = int(row.revision or 0)
        if expected_revision is not None and expected_revision not in {-1} and current != expected_revision:
            raise RevisionConflictError(expected=expected_revision, actual=current)
        row.revision = revision
        row.etag = etag
        row.payload = payload
        row.updated_by = updated_by
        row.updated_at = now
    session.flush()
    return _draft_from_row(row)


def get_published_row(session: Session, *, tenant_id: str) -> PublishedRow | None:
    row = session.get(TenantCmPublishedStateRow, tenant_id)
    return _published_from_row(row) if row is not None else None


def upsert_published_row(
    session: Session,
    *,
    tenant_id: str,
    expected_revision: int | None,
    revision: int,
    content_version_id: str,
    index_version_id: str,
    checksums: dict[str, Any],
    actions_payload: dict[str, Any],
    embedding_provider: str,
    embedding_model: str,
    embedding_dimensions: int,
    embedding_version: str,
    schema_version: int,
    published_at: float,
) -> PublishedRow:
    row = session.get(TenantCmPublishedStateRow, tenant_id)
    now = time.time()
    if row is None:
        if expected_revision not in {None, -1, 0}:
            raise RevisionConflictError(expected=expected_revision or 0, actual=None)
        row = TenantCmPublishedStateRow(
            tenant_id=tenant_id,
            content_version_id=content_version_id,
            index_version_id=index_version_id,
            checksums=checksums,
            actions_payload=actions_payload,
            embedding_provider=embedding_provider,
            embedding_model=embedding_model,
            embedding_dimensions=embedding_dimensions,
            embedding_version=embedding_version,
            schema_version=schema_version,
            revision=revision,
            published_at=published_at,
            updated_at=now,
        )
        session.add(row)
    else:
        current = int(row.revision or 0)
        if expected_revision is not None and expected_revision not in {-1} and current != expected_revision:
            raise RevisionConflictError(expected=expected_revision, actual=current)
        row.content_version_id = content_version_id
        row.index_version_id = index_version_id
        row.checksums = checksums
        row.actions_payload = actions_payload
        row.embedding_provider = embedding_provider
        row.embedding_model = embedding_model
        row.embedding_dimensions = embedding_dimensions
        row.embedding_version = embedding_version
        row.schema_version = schema_version
        row.revision = revision
        row.published_at = published_at
        row.updated_at = now
    session.flush()
    return _published_from_row(row)


def get_comment_asset_row(session: Session, *, tenant_id: str, asset_key: str) -> CommentAssetRow | None:
    row = session.get(TenantMetaCommentAssetSettingRow, {"tenant_id": tenant_id, "asset_key": asset_key})
    if row is None:
        return None
    return CommentAssetRow(
        tenant_id=row.tenant_id,
        asset_key=row.asset_key,
        app_key=str(row.app_key or ""),
        channel=str(row.channel or ""),
        asset_id=str(row.asset_id or ""),
        enabled=bool(row.enabled),
        instructions=str(row.instructions or ""),
        revision=int(row.revision or 0),
        updated_at=float(row.updated_at or 0),
    )


def list_comment_asset_rows(session: Session, *, tenant_id: str) -> list[CommentAssetRow]:
    rows = session.scalars(
        select(TenantMetaCommentAssetSettingRow).where(TenantMetaCommentAssetSettingRow.tenant_id == tenant_id)
    ).all()
    return [
        CommentAssetRow(
            tenant_id=row.tenant_id,
            asset_key=row.asset_key,
            app_key=str(row.app_key or ""),
            channel=str(row.channel or ""),
            asset_id=str(row.asset_id or ""),
            enabled=bool(row.enabled),
            instructions=str(row.instructions or ""),
            revision=int(row.revision or 0),
            updated_at=float(row.updated_at or 0),
        )
        for row in rows
    ]


def upsert_comment_asset_row(
    session: Session,
    *,
    tenant_id: str,
    asset_key: str,
    app_key: str,
    channel: str,
    asset_id: str,
    enabled: bool,
    instructions: str,
    expected_revision: int | None,
    revision: int,
) -> CommentAssetRow:
    row = session.get(TenantMetaCommentAssetSettingRow, {"tenant_id": tenant_id, "asset_key": asset_key})
    now = time.time()
    if row is None:
        row = TenantMetaCommentAssetSettingRow(
            tenant_id=tenant_id,
            asset_key=asset_key,
            app_key=app_key,
            channel=channel,
            asset_id=asset_id,
            enabled=enabled,
            instructions=instructions,
            revision=revision,
            updated_at=now,
        )
        session.add(row)
    else:
        current = int(row.revision or 0)
        if expected_revision is not None and expected_revision not in {-1} and current != expected_revision:
            raise RevisionConflictError(expected=expected_revision, actual=current)
        row.app_key = app_key
        row.channel = channel
        row.asset_id = asset_id
        row.enabled = enabled
        row.instructions = instructions
        row.revision = revision
        row.updated_at = now
    session.flush()
    return get_comment_asset_row(session, tenant_id=tenant_id, asset_key=asset_key)  # type: ignore[return-value]


def get_sync_cursor(session: Session, *, binding_id: str, cursor_key: str) -> str | None:
    row = session.get(MetaCommentSyncCursorRow, {"binding_id": binding_id, "cursor_key": cursor_key})
    return str(row.cursor_value) if row is not None else None


def upsert_sync_cursor(
    session: Session,
    *,
    binding_id: str,
    cursor_key: str,
    cursor_value: str,
    expected_revision: int | None,
    revision: int,
) -> None:
    row = session.get(MetaCommentSyncCursorRow, {"binding_id": binding_id, "cursor_key": cursor_key})
    now = time.time()
    if row is None:
        row = MetaCommentSyncCursorRow(
            binding_id=binding_id,
            cursor_key=cursor_key,
            cursor_value=cursor_value,
            revision=revision,
            updated_at=now,
        )
        session.add(row)
    else:
        current = int(row.revision or 0)
        if expected_revision is not None and expected_revision not in {-1} and current != expected_revision:
            raise RevisionConflictError(expected=expected_revision, actual=current)
        row.cursor_value = cursor_value
        row.revision = revision
        row.updated_at = now
    session.flush()


def migration_applied(session: Session, *, tenant_id: str, migration_id: str) -> bool:
    row = session.get(TenantRuntimeConfigMigrationRow, {"tenant_id": tenant_id, "migration_id": migration_id})
    return row is not None


def record_migration(
    session: Session,
    *,
    tenant_id: str,
    migration_id: str,
    audit: dict[str, Any],
) -> None:
    if migration_applied(session, tenant_id=tenant_id, migration_id=migration_id):
        return
    row = TenantRuntimeConfigMigrationRow(
        tenant_id=tenant_id,
        migration_id=migration_id,
        applied_at=time.time(),
        audit=audit,
    )
    session.add(row)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        raise
