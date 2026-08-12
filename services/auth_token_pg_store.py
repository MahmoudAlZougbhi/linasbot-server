"""Postgres persistence for mobile refresh + auth email tokens."""

from __future__ import annotations

from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models.billing_auth import AuthEmailTokenRow, MobileRefreshTokenRow

TokenPurpose = Literal["password_reset", "email_verify", "email_change"]


def mobile_issue(
    session: Session,
    *,
    token_hash: str,
    user_id: str,
    email: str,
    tenant_id: str,
    session_id: str,
    created_at: float,
    expires_at: float,
) -> None:
    session.add(
        MobileRefreshTokenRow(
            token_hash=token_hash,
            user_id=user_id,
            email=email,
            tenant_id=tenant_id,
            session_id=session_id,
            created_at=created_at,
            expires_at=expires_at,
            revoked_at=None,
        )
    )
    session.flush()


def mobile_get(session: Session, token_hash: str) -> MobileRefreshTokenRow | None:
    return session.get(MobileRefreshTokenRow, token_hash)


def mobile_revoke(session: Session, row: MobileRefreshTokenRow, revoked_at: float) -> None:
    row.revoked_at = revoked_at
    session.flush()


def mobile_delete(session: Session, token_hash: str) -> None:
    row = session.get(MobileRefreshTokenRow, token_hash)
    if row is not None:
        session.delete(row)
        session.flush()


def mobile_revoke_all_for_user(session: Session, user_id: str, revoked_at: float) -> int:
    rows = session.scalars(
        select(MobileRefreshTokenRow).where(
            MobileRefreshTokenRow.user_id == user_id,
            MobileRefreshTokenRow.revoked_at.is_(None),
        )
    ).all()
    for row in rows:
        row.revoked_at = revoked_at
    session.flush()
    return len(rows)


def email_issue(
    session: Session,
    *,
    token_hash: str,
    purpose: TokenPurpose,
    user_id: str,
    email: str,
    tenant_id: str,
    created_at: float,
    expires_at: float,
    meta: dict[str, Any] | None,
) -> None:
    session.add(
        AuthEmailTokenRow(
            token_hash=token_hash,
            purpose=purpose,
            user_id=user_id,
            email=email,
            tenant_id=tenant_id,
            created_at=created_at,
            expires_at=expires_at,
            used_at=None,
            meta=dict(meta) if meta else None,
        )
    )
    session.flush()


def email_get(session: Session, token_hash: str) -> AuthEmailTokenRow | None:
    return session.get(AuthEmailTokenRow, token_hash)


def email_mark_used(session: Session, row: AuthEmailTokenRow, used_at: float) -> None:
    row.used_at = used_at
    session.flush()


def email_delete_unused_for_user(
    session: Session,
    user_id: str,
    purpose: TokenPurpose | None = None,
) -> int:
    stmt = select(AuthEmailTokenRow).where(
        AuthEmailTokenRow.user_id == user_id,
        AuthEmailTokenRow.used_at.is_(None),
    )
    if purpose:
        stmt = stmt.where(AuthEmailTokenRow.purpose == purpose)
    rows = session.scalars(stmt).all()
    for row in rows:
        session.delete(row)
    session.flush()
    return len(rows)


def upsert_mobile_refresh(session: Session, token_hash: str, data: dict[str, Any]) -> None:
    row = session.get(MobileRefreshTokenRow, token_hash)
    if row is None:
        row = MobileRefreshTokenRow(token_hash=token_hash, user_id=str(data["user_id"]), tenant_id=str(data["tenant_id"]))
        session.add(row)
    row.email = str(data.get("email") or "")
    row.session_id = str(data.get("session_id") or "")
    row.created_at = float(data["created_at"])
    row.expires_at = float(data["expires_at"])
    revoked = data.get("revoked_at")
    row.revoked_at = float(revoked) if revoked is not None else None
    session.flush()


def upsert_auth_email_token(session: Session, token_hash: str, data: dict[str, Any]) -> None:
    row = session.get(AuthEmailTokenRow, token_hash)
    if row is None:
        row = AuthEmailTokenRow(
            token_hash=token_hash,
            purpose=str(data["purpose"]),
            user_id=str(data["user_id"]),
            tenant_id=str(data["tenant_id"]),
        )
        session.add(row)
    row.email = str(data.get("email") or "")
    row.created_at = float(data["created_at"])
    row.expires_at = float(data["expires_at"])
    used = data.get("used_at")
    row.used_at = float(used) if used is not None else None
    meta = data.get("meta")
    row.meta = dict(meta) if isinstance(meta, dict) else None
    session.flush()
