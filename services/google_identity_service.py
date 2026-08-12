"""PG-backed Google external identity (AuthExternalIdentityRow, provider=google)."""

from __future__ import annotations

import hashlib
import logging
import time
import uuid
from typing import Any

from sqlalchemy import select

from db.models.apple_billing import AuthExternalIdentityRow
from db.session import whatsapp_session
from services.user_service import user_service

logger = logging.getLogger(__name__)

PROVIDER_GOOGLE = "google"


class GoogleIdentityError(ValueError):
    """Google identity link/unlink policy violation."""


def _uid_tag(user_id: str) -> str:
    return hashlib.sha256(str(user_id).encode("utf-8")).hexdigest()[:12]


def _row_to_dict(row: AuthExternalIdentityRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "tenant_id": row.tenant_id,
        "user_id": row.user_id,
        "provider": row.provider,
        "provider_subject": row.provider_subject,
        "email": row.email,
        "email_is_private_relay": bool(row.email_is_private_relay),
        "display_name": row.display_name,
        "linked_at": float(row.linked_at or 0),
        "unlinked_at": float(row.unlinked_at) if row.unlinked_at is not None else None,
        "meta": dict(row.meta or {}),
    }


def find_by_google_sub(sub: str) -> dict[str, Any] | None:
    subject = (sub or "").strip()
    if not subject:
        return None
    with whatsapp_session() as session:
        row = session.execute(
            select(AuthExternalIdentityRow).where(
                AuthExternalIdentityRow.provider == PROVIDER_GOOGLE,
                AuthExternalIdentityRow.provider_subject == subject,
                AuthExternalIdentityRow.unlinked_at.is_(None),
            )
        ).scalar_one_or_none()
        return _row_to_dict(row) if row else None


def find_active_google_sub_for_user(user_id: str) -> str | None:
    uid = (user_id or "").strip()
    if not uid:
        return None
    with whatsapp_session() as session:
        row = session.execute(
            select(AuthExternalIdentityRow).where(
                AuthExternalIdentityRow.provider == PROVIDER_GOOGLE,
                AuthExternalIdentityRow.user_id == uid,
                AuthExternalIdentityRow.unlinked_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        sub = str(row.provider_subject or "").strip()
        return sub or None


def _find_any_google_row(session: Any, sub: str) -> AuthExternalIdentityRow | None:
    row = session.execute(
        select(AuthExternalIdentityRow).where(
            AuthExternalIdentityRow.provider == PROVIDER_GOOGLE,
            AuthExternalIdentityRow.provider_subject == sub,
        )
    ).scalar_one_or_none()
    return row if isinstance(row, AuthExternalIdentityRow) else None


def link_google_identity(
    *,
    tenant_id: str,
    user_id: str,
    sub: str,
    email: str | None,
    display_name: str | None = None,
) -> dict[str, Any]:
    subject = (sub or "").strip()
    uid = (user_id or "").strip()
    tid = (tenant_id or "").strip()
    if not subject or not uid or not tid:
        raise GoogleIdentityError("tenant_id, user_id, and sub required")

    now = time.time()
    with whatsapp_session() as session:
        existing = _find_any_google_row(session, subject)
        if existing is not None:
            if existing.unlinked_at is None and str(existing.user_id) != uid:
                raise GoogleIdentityError("google_sub_linked_to_other_user")
            existing.user_id = uid
            existing.tenant_id = tid
            existing.unlinked_at = None
            if email:
                existing.email = email
            if display_name:
                existing.display_name = display_name[:120]
            if not existing.linked_at:
                existing.linked_at = now
            session.flush()
            logger.info("google_identity_relinked uid=%s", _uid_tag(uid))
            return _row_to_dict(existing)

        other = session.execute(
            select(AuthExternalIdentityRow).where(
                AuthExternalIdentityRow.provider == PROVIDER_GOOGLE,
                AuthExternalIdentityRow.user_id == uid,
                AuthExternalIdentityRow.unlinked_at.is_(None),
            )
        ).scalar_one_or_none()
        if other is not None and str(other.provider_subject) != subject:
            raise GoogleIdentityError("user_already_has_google_identity")

        row = AuthExternalIdentityRow(
            id=str(uuid.uuid4()),
            tenant_id=tid,
            user_id=uid,
            provider=PROVIDER_GOOGLE,
            provider_subject=subject,
            email=email,
            email_is_private_relay=False,
            display_name=(display_name or "")[:120] or None,
            linked_at=now,
            unlinked_at=None,
            meta={},
        )
        session.add(row)
        session.flush()
        logger.info("google_identity_linked uid=%s", _uid_tag(uid))
        return _row_to_dict(row)


def unlink_google_identity(*, user_id: str, sub: str) -> None:
    uid = (user_id or "").strip()
    subject = (sub or "").strip()
    if not uid or not subject:
        raise GoogleIdentityError("user_id and sub required")

    with whatsapp_session() as session:
        row = session.execute(
            select(AuthExternalIdentityRow).where(
                AuthExternalIdentityRow.provider == PROVIDER_GOOGLE,
                AuthExternalIdentityRow.provider_subject == subject,
                AuthExternalIdentityRow.user_id == uid,
                AuthExternalIdentityRow.unlinked_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise GoogleIdentityError("google_identity_not_found")

        # Prevent lock-out: require password login or another provider.
        user = user_service.get_user_by_id(uid)
        password_ok = bool(user and user.get("passwordLoginEnabled"))
        other_providers = session.execute(
            select(AuthExternalIdentityRow).where(
                AuthExternalIdentityRow.user_id == uid,
                AuthExternalIdentityRow.unlinked_at.is_(None),
                AuthExternalIdentityRow.provider != PROVIDER_GOOGLE,
            )
        ).scalars().all()
        if not password_ok and not other_providers:
            raise GoogleIdentityError("cannot_unlink_last_sign_in_method")

        row.unlinked_at = time.time()
        session.flush()
        logger.info("google_identity_unlinked uid=%s", _uid_tag(uid))
