"""PG-backed Apple external identity + appAccountToken binding."""

from __future__ import annotations

import hashlib
import logging
import time
import uuid
from typing import Any

from sqlalchemy import select

from db.models.apple_billing import AppleAppAccountTokenRow, AuthExternalIdentityRow
from db.session import whatsapp_session
from services.apple_sign_in_service import is_private_relay_email
from services.user_service import user_service

logger = logging.getLogger(__name__)

PROVIDER_APPLE = "apple"


class AppleIdentityError(ValueError):
    """Apple identity link/unlink policy violation."""


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


def find_by_apple_sub(sub: str) -> dict[str, Any] | None:
    """Return active Apple identity for ``sub`` (unlinked_at is None), or None."""
    subject = (sub or "").strip()
    if not subject:
        return None
    with whatsapp_session() as session:
        row = session.execute(
            select(AuthExternalIdentityRow).where(
                AuthExternalIdentityRow.provider == PROVIDER_APPLE,
                AuthExternalIdentityRow.provider_subject == subject,
                AuthExternalIdentityRow.unlinked_at.is_(None),
            )
        ).scalar_one_or_none()
        return _row_to_dict(row) if row else None


def _find_any_apple_row(session: Any, sub: str) -> AuthExternalIdentityRow | None:
    row = session.execute(
        select(AuthExternalIdentityRow).where(
            AuthExternalIdentityRow.provider == PROVIDER_APPLE,
            AuthExternalIdentityRow.provider_subject == sub,
        )
    ).scalar_one_or_none()
    return row if isinstance(row, AuthExternalIdentityRow) else None


def link_apple_identity(
    *,
    tenant_id: str,
    user_id: str,
    sub: str,
    email: str | None,
    is_private_relay: bool | None = None,
    display_name: str | None = None,
) -> dict[str, Any]:
    """
    Link Apple ``sub`` to user. Refuse if sub is already tied to a different user
    (including previously unlinked rows — unique constraint keeps the subject).
    Does not auto-merge solely because email matches.
    """
    subject = (sub or "").strip()
    tid = (tenant_id or "").strip()
    uid = (user_id or "").strip()
    if not subject or not tid or not uid:
        raise AppleIdentityError("tenant_id, user_id, and sub are required")

    email_n = (email or "").strip().lower() or None
    relay = bool(is_private_relay) if is_private_relay is not None else is_private_relay_email(email_n)
    name = (display_name or "").strip()[:255] or None
    now = time.time()

    with whatsapp_session() as session:
        existing = _find_any_apple_row(session, subject)
        if existing is not None:
            if str(existing.user_id) != uid:
                logger.info(
                    "apple_identity link refused: sub taken owner=%s requester=%s",
                    _uid_tag(str(existing.user_id)),
                    _uid_tag(uid),
                )
                raise AppleIdentityError("Apple identity already linked to another account")
            # Same user: re-activate if unlinked, refresh non-PII metadata lightly.
            existing.unlinked_at = None
            existing.tenant_id = tid
            if email_n:
                existing.email = email_n
                existing.email_is_private_relay = relay
            if name:
                existing.display_name = name
            if not existing.linked_at:
                existing.linked_at = now
            session.flush()
            out = _row_to_dict(existing)
            logger.info("apple_identity re-linked user=%s", _uid_tag(uid))
            return out

        row = AuthExternalIdentityRow(
            id=str(uuid.uuid4()),
            tenant_id=tid,
            user_id=uid,
            provider=PROVIDER_APPLE,
            provider_subject=subject,
            email=email_n,
            email_is_private_relay=relay,
            display_name=name,
            linked_at=now,
            unlinked_at=None,
            meta={},
        )
        session.add(row)
        session.flush()
        out = _row_to_dict(row)
        logger.info("apple_identity linked user=%s", _uid_tag(uid))
        return out


def list_active_providers_for_user(user_id: str) -> list[str]:
    uid = (user_id or "").strip()
    if not uid:
        return []
    with whatsapp_session() as session:
        rows = (
            session.execute(
                select(AuthExternalIdentityRow.provider).where(
                    AuthExternalIdentityRow.user_id == uid,
                    AuthExternalIdentityRow.unlinked_at.is_(None),
                )
            )
            .scalars()
            .all()
        )
        return sorted({str(p) for p in rows if p})


def user_has_password_login(user: dict[str, Any] | None) -> bool:
    """True when password login is enabled (legacy users default True if password hash exists)."""
    if not user:
        return False
    if "passwordLoginEnabled" in user:
        return bool(user.get("passwordLoginEnabled"))
    return bool(str(user.get("password") or "").strip())


def user_has_other_login_method(*, user_id: str, excluding_apple_sub: str | None = None) -> bool:
    uid = (user_id or "").strip()
    user = user_service.get_user_by_id(uid)
    if user_has_password_login(user):
        return True
    providers = list_active_providers_for_user(uid)
    if excluding_apple_sub:
        # Count non-apple providers, or other apple rows (unlikely).
        with whatsapp_session() as session:
            rows = (
                session.execute(
                    select(AuthExternalIdentityRow).where(
                        AuthExternalIdentityRow.user_id == uid,
                        AuthExternalIdentityRow.unlinked_at.is_(None),
                    )
                )
                .scalars()
                .all()
            )
            for row in rows:
                if row.provider == PROVIDER_APPLE and row.provider_subject == excluding_apple_sub:
                    continue
                return True
        return False
    return len(providers) > 1 or (len(providers) == 1 and providers[0] != PROVIDER_APPLE)


def unlink_apple_identity(*, user_id: str, sub: str) -> dict[str, Any]:
    """Unlink Apple only when another login method remains."""
    uid = (user_id or "").strip()
    subject = (sub or "").strip()
    if not uid or not subject:
        raise AppleIdentityError("user_id and sub are required")

    if not user_has_other_login_method(user_id=uid, excluding_apple_sub=subject):
        raise AppleIdentityError("Cannot unlink Apple — another login method is required")

    with whatsapp_session() as session:
        row = session.execute(
            select(AuthExternalIdentityRow).where(
                AuthExternalIdentityRow.provider == PROVIDER_APPLE,
                AuthExternalIdentityRow.provider_subject == subject,
                AuthExternalIdentityRow.user_id == uid,
                AuthExternalIdentityRow.unlinked_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise AppleIdentityError("Apple identity not found for user")
        row.unlinked_at = time.time()
        session.flush()
        out = _row_to_dict(row)
        logger.info("apple_identity unlinked user=%s", _uid_tag(uid))
        return out


def unlink_all_apple_for_user(user_id: str) -> int:
    """Soft-unlink all active Apple identities for account deletion (no other-login check)."""
    uid = (user_id or "").strip()
    if not uid:
        return 0
    now = time.time()
    count = 0
    with whatsapp_session() as session:
        rows = (
            session.execute(
                select(AuthExternalIdentityRow).where(
                    AuthExternalIdentityRow.provider == PROVIDER_APPLE,
                    AuthExternalIdentityRow.user_id == uid,
                    AuthExternalIdentityRow.unlinked_at.is_(None),
                )
            )
            .scalars()
            .all()
        )
        for row in rows:
            row.unlinked_at = now
            count += 1
        session.flush()
    if count:
        logger.info("apple_identity bulk unlink user=%s count=%s", _uid_tag(uid), count)
    return count


def get_or_create_app_account_token(tenant_id: str, user_id: str) -> str:
    """Return stable UUID4 appAccountToken for (tenant_id, user_id)."""
    tid = (tenant_id or "").strip()
    uid = (user_id or "").strip()
    if not tid or not uid:
        raise AppleIdentityError("tenant_id and user_id are required")

    with whatsapp_session() as session:
        existing = session.execute(
            select(AppleAppAccountTokenRow).where(
                AppleAppAccountTokenRow.tenant_id == tid,
                AppleAppAccountTokenRow.user_id == uid,
            )
        ).scalar_one_or_none()
        if existing is not None:
            return str(existing.app_account_token)

        token = str(uuid.uuid4())
        session.add(
            AppleAppAccountTokenRow(
                app_account_token=token,
                tenant_id=tid,
                user_id=uid,
                created_at=time.time(),
            )
        )
        session.flush()
        logger.info("apple_app_account_token created user=%s", _uid_tag(uid))
        return token
