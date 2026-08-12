"""Durable Apple token-revoke outbox stored in AuthExternalIdentityRow.meta.

No new Alembic migration: pending jobs live under meta keys
``apple_revoke_pending`` and ``apple_refresh_token``.
Never log raw tokens.
"""

from __future__ import annotations

import hashlib
import logging
import time
from typing import Any

from sqlalchemy import select

from db.models.apple_billing import AuthExternalIdentityRow
from db.session import whatsapp_session
from services.apple_identity_service import PROVIDER_APPLE
from services.apple_token_revoke import (
    AppleTokenRevokeError,
    exchange_authorization_code,
    revoke_apple_token,
)

logger = logging.getLogger(__name__)

META_REFRESH = "apple_refresh_token"
META_PENDING = "apple_revoke_pending"
_MAX_BACKOFF_SEC = 3600


def _uid_tag(user_id: str) -> str:
    return hashlib.sha256(str(user_id).encode("utf-8")).hexdigest()[:12]


def _token_fingerprint(token: str) -> str:
    return hashlib.sha256(str(token).encode("utf-8")).hexdigest()[:12]


def _backoff_seconds(attempts: int) -> float:
    n = max(0, int(attempts))
    return float(min(_MAX_BACKOFF_SEC, 30 * (2**n)))


def _pending_dict(
    *,
    hint: str,
    attempts: int = 0,
    last_error: str | None = None,
    enqueued_at: float | None = None,
    token_fp: str | None = None,
) -> dict[str, Any]:
    now = time.time()
    return {
        "token_type_hint": hint,
        "attempts": int(attempts),
        "next_attempt_at": now if attempts <= 0 else now + _backoff_seconds(attempts),
        "last_error": last_error,
        "enqueued_at": float(enqueued_at if enqueued_at is not None else now),
        "token_fp": token_fp,
    }


def store_apple_refresh_token(*, user_id: str, sub: str, refresh_token: str) -> bool:
    """Persist refresh_token on the Apple identity meta for later revoke."""
    uid = (user_id or "").strip()
    subject = (sub or "").strip()
    token = (refresh_token or "").strip()
    if not uid or not subject or not token:
        return False
    with whatsapp_session() as session:
        row = session.execute(
            select(AuthExternalIdentityRow).where(
                AuthExternalIdentityRow.provider == PROVIDER_APPLE,
                AuthExternalIdentityRow.provider_subject == subject,
                AuthExternalIdentityRow.user_id == uid,
            )
        ).scalar_one_or_none()
        if row is None:
            return False
        meta = dict(row.meta or {})
        meta[META_REFRESH] = token
        row.meta = meta
        session.flush()
    logger.info(
        "apple_refresh_stored user=%s sub_fp=%s token_fp=%s",
        _uid_tag(uid),
        _token_fingerprint(subject),
        _token_fingerprint(token),
    )
    return True


def maybe_store_refresh_from_authorization_code(
    *,
    user_id: str,
    sub: str,
    authorization_code: str | None,
) -> bool:
    code = (authorization_code or "").strip()
    if not code:
        return False
    try:
        tokens = exchange_authorization_code(code)
    except AppleTokenRevokeError as exc:
        logger.info(
            "apple_refresh_exchange_failed user=%s err=%s",
            _uid_tag(user_id),
            type(exc).__name__,
        )
        return False
    refresh = str(tokens.get("refresh_token") or "").strip()
    if not refresh:
        return False
    return store_apple_refresh_token(user_id=user_id, sub=sub, refresh_token=refresh)


def _rows_for_user(session: Any, user_id: str) -> list[AuthExternalIdentityRow]:
    return list(
        session.execute(
            select(AuthExternalIdentityRow).where(
                AuthExternalIdentityRow.provider == PROVIDER_APPLE,
                AuthExternalIdentityRow.user_id == user_id,
            )
        )
        .scalars()
        .all()
    )


def enqueue_revoke(user_id: str, token: str, hint: str = "refresh_token") -> bool:
    """Persist durable pending revoke on the user's Apple identity meta."""
    uid = (user_id or "").strip()
    value = (token or "").strip()
    token_hint = (hint or "refresh_token").strip() or "refresh_token"
    if not uid or not value:
        return False
    fp = _token_fingerprint(value)
    pending = _pending_dict(hint=token_hint, attempts=0, token_fp=fp)
    with whatsapp_session() as session:
        rows = _rows_for_user(session, uid)
        if not rows:
            logger.info("apple_revoke_enqueue_no_identity user=%s", _uid_tag(uid))
            return False
        for row in rows:
            meta = dict(row.meta or {})
            meta[META_REFRESH] = value
            meta[META_PENDING] = pending
            row.meta = meta
        session.flush()
    logger.info(
        "apple_revoke_enqueued user=%s hint=%s token_fp=%s",
        _uid_tag(uid),
        token_hint,
        fp,
    )
    return True


def _clear_pending_on_row(row: AuthExternalIdentityRow) -> None:
    meta = dict(row.meta or {})
    meta.pop(META_PENDING, None)
    meta.pop(META_REFRESH, None)
    row.meta = meta


def clear_revoke_pending(user_id: str) -> None:
    uid = (user_id or "").strip()
    if not uid:
        return
    with whatsapp_session() as session:
        for row in _rows_for_user(session, uid):
            _clear_pending_on_row(row)
        session.flush()


def _load_stored_token(user_id: str) -> tuple[str | None, str]:
    uid = (user_id or "").strip()
    if not uid:
        return None, "refresh_token"
    with whatsapp_session() as session:
        for row in _rows_for_user(session, uid):
            meta = dict(row.meta or {})
            token = str(meta.get(META_REFRESH) or "").strip()
            if token:
                pending = meta.get(META_PENDING)
                hint = "refresh_token"
                if isinstance(pending, dict):
                    hint = str(pending.get("token_type_hint") or hint)
                return token, hint
    return None, "refresh_token"


def revoke_on_account_delete(*, user_id: str, authorization_code: str | None = None) -> dict[str, Any]:
    """Enqueue durable revoke + attempt immediately. Never silently drop a known token."""
    uid = (user_id or "").strip()
    code = (authorization_code or "").strip() or None
    token: str | None = None
    hint = "refresh_token"

    if code:
        try:
            tokens = exchange_authorization_code(code)
            refresh = str(tokens.get("refresh_token") or "").strip()
            access = str(tokens.get("access_token") or "").strip()
            if refresh:
                token, hint = refresh, "refresh_token"
            elif access:
                token, hint = access, "access_token"
        except AppleTokenRevokeError as exc:
            logger.info(
                "apple_revoke_delete_exchange_failed user=%s err=%s",
                _uid_tag(uid),
                type(exc).__name__,
            )

    if not token:
        token, hint = _load_stored_token(uid)

    if not token:
        logger.info("apple_revoke_delete_no_token user=%s", _uid_tag(uid))
        return {"enqueued": False, "revoked": False, "reason": "no_token"}

    enqueued = enqueue_revoke(uid, token, hint)
    try:
        revoke_apple_token(token, hint)
    except AppleTokenRevokeError as exc:
        logger.info(
            "apple_revoke_delete_immediate_failed user=%s err=%s enqueued=%s",
            _uid_tag(uid),
            type(exc).__name__,
            enqueued,
        )
        return {"enqueued": enqueued, "revoked": False, "reason": "http_failed"}

    clear_revoke_pending(uid)
    return {"enqueued": enqueued, "revoked": True, "reason": "ok"}


def process_pending_revokes(limit: int = 25) -> dict[str, Any]:
    """Retry pending revokes with meta backoff. Returns counters only."""
    lim = max(1, min(int(limit), 100))
    now = time.time()
    scanned = 0
    attempted = 0
    succeeded = 0
    failed = 0

    with whatsapp_session() as session:
        rows = list(
            session.execute(
                select(AuthExternalIdentityRow).where(
                    AuthExternalIdentityRow.provider == PROVIDER_APPLE,
                ).limit(500)
            )
            .scalars()
            .all()
        )
        for row in rows:
            meta = dict(row.meta or {})
            pending = meta.get(META_PENDING)
            if not pending:
                continue
            scanned += 1
            if attempted >= lim:
                break
            if isinstance(pending, dict):
                next_at = float(pending.get("next_attempt_at") or 0)
                if next_at > now:
                    continue
                hint = str(pending.get("token_type_hint") or "refresh_token")
                attempts = int(pending.get("attempts") or 0)
                enqueued_at = float(pending.get("enqueued_at") or now)
            else:
                hint = "refresh_token"
                attempts = 0
                enqueued_at = now

            token = str(meta.get(META_REFRESH) or "").strip()
            if not token:
                meta.pop(META_PENDING, None)
                row.meta = meta
                continue

            attempted += 1
            try:
                revoke_apple_token(token, hint)
            except AppleTokenRevokeError as exc:
                failed += 1
                meta[META_PENDING] = _pending_dict(
                    hint=hint,
                    attempts=attempts + 1,
                    last_error=type(exc).__name__,
                    enqueued_at=enqueued_at,
                    token_fp=_token_fingerprint(token),
                )
                row.meta = meta
                logger.info(
                    "apple_revoke_retry_failed user=%s attempts=%s err=%s",
                    _uid_tag(str(row.user_id)),
                    attempts + 1,
                    type(exc).__name__,
                )
                continue

            _clear_pending_on_row(row)
            succeeded += 1
            logger.info("apple_revoke_retry_ok user=%s", _uid_tag(str(row.user_id)))
        session.flush()

    return {
        "scanned": scanned,
        "attempted": attempted,
        "succeeded": succeeded,
        "failed": failed,
    }
