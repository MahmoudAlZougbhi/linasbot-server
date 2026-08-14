"""Password-reset and email-verification token store (file or Postgres).

Tokens are single-use, time-limited, and stored as SHA-256 hashes — raw tokens
never persist. CSRF is not required for public token redeem endpoints; rate
limits apply at the API layer.

email_verify and password_reset also store a 6-digit OTP namespaced by email so
the existing redeem endpoints accept either the email-link token or the code.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from services.billing_backend import auth_tokens_use_postgres, require_auth_token_pg_session
from storage.persistent_storage import _DATA_ROOT

TokenPurpose = Literal["password_reset", "email_verify", "email_change"]
_OTP_PURPOSES = frozenset({"password_reset", "email_verify"})

PASSWORD_RESET_TTL_SECONDS = int(os.getenv("PASSWORD_RESET_TTL_SECONDS", str(60 * 60)))
EMAIL_VERIFY_TTL_SECONDS = int(os.getenv("EMAIL_VERIFY_TTL_SECONDS", str(48 * 60 * 60)))
EMAIL_CHANGE_TTL_SECONDS = int(os.getenv("EMAIL_CHANGE_TTL_SECONDS", str(24 * 60 * 60)))


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def otp_secret(purpose: TokenPurpose, email: str, code: str) -> str:
    return f"otp:{purpose}:{(email or '').strip().lower()}:{(code or '').strip()}"


class IssuedAuthEmailToken(str):
    """URL-safe link token (str) plus `.otp` when a 6-digit code was issued."""

    otp: str

    def __new__(cls, raw: str, otp: str = "") -> IssuedAuthEmailToken:
        obj = str.__new__(cls, raw)
        obj.otp = otp
        return obj


@dataclass(frozen=True)
class AuthEmailTokenRecord:
    purpose: TokenPurpose
    user_id: str
    email: str
    tenant_id: str
    created_at: float
    expires_at: float
    used_at: float | None = None
    meta: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "purpose": self.purpose,
            "user_id": self.user_id,
            "email": self.email,
            "tenant_id": self.tenant_id,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "used_at": self.used_at,
        }
        if self.meta:
            payload["meta"] = self.meta
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AuthEmailTokenRecord:
        tenant_id = str(data.get("tenant_id") or "").strip()
        if not tenant_id:
            raise ValueError("tenant_id required")
        meta = data.get("meta")
        return cls(
            purpose=data["purpose"],  # type: ignore[arg-type]
            user_id=str(data["user_id"]),
            email=str(data["email"]),
            tenant_id=tenant_id,
            created_at=float(data["created_at"]),
            expires_at=float(data["expires_at"]),
            used_at=float(data["used_at"]) if data.get("used_at") is not None else None,
            meta=dict(meta) if isinstance(meta, dict) else None,
        )


def _row_to_record(row: Any) -> AuthEmailTokenRecord:
    return AuthEmailTokenRecord(
        purpose=row.purpose,  # type: ignore[arg-type]
        user_id=row.user_id,
        email=row.email,
        tenant_id=row.tenant_id,
        created_at=float(row.created_at),
        expires_at=float(row.expires_at),
        used_at=float(row.used_at) if row.used_at is not None else None,
        meta=dict(row.meta) if isinstance(row.meta, dict) else None,
    )


def _with_used(record: AuthEmailTokenRecord, used_at: float) -> AuthEmailTokenRecord:
    return AuthEmailTokenRecord(
        purpose=record.purpose,
        user_id=record.user_id,
        email=record.email,
        tenant_id=record.tenant_id,
        created_at=record.created_at,
        expires_at=record.expires_at,
        used_at=used_at,
        meta=record.meta,
    )


class AuthEmailTokenService:
    def __init__(self, store_dir: Path | None = None) -> None:
        self._lock = threading.RLock()
        self._store_dir = store_dir or (Path(_DATA_ROOT) / "auth" / "email_tokens")
        self._store_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, token_hash: str) -> Path:
        return self._store_dir / f"{token_hash}.json"

    def issue(
        self,
        *,
        purpose: TokenPurpose,
        user_id: str,
        email: str,
        tenant_id: str,
        ttl_seconds: int | None = None,
        meta: dict[str, Any] | None = None,
    ) -> IssuedAuthEmailToken:
        tid = str(tenant_id or "").strip()
        if not tid:
            raise ValueError("tenant_id required")
        raw = secrets.token_urlsafe(32)
        token_hash = _hash_token(raw)
        now = time.time()
        if ttl_seconds is None:
            if purpose == "password_reset":
                ttl_seconds = PASSWORD_RESET_TTL_SECONDS
            elif purpose == "email_change":
                ttl_seconds = EMAIL_CHANGE_TTL_SECONDS
            else:
                ttl_seconds = EMAIL_VERIFY_TTL_SECONDS
        email_n = (email or "").strip().lower()
        otp = f"{secrets.randbelow(1_000_000):06d}" if purpose in _OTP_PURPOSES else ""
        otp_hash = _hash_token(otp_secret(purpose, email_n, otp)) if otp else ""
        base_meta = dict(meta) if isinstance(meta, dict) else {}
        link_meta = dict(base_meta)
        if otp_hash:
            link_meta["peer_hash"] = otp_hash
        record = AuthEmailTokenRecord(
            purpose=purpose,
            user_id=user_id,
            email=email_n,
            tenant_id=tid,
            created_at=now,
            expires_at=now + max(60, int(ttl_seconds)),
            meta=link_meta or None,
        )
        if auth_tokens_use_postgres():
            from services.auth_token_pg_store import email_issue

            with require_auth_token_pg_session() as session:
                email_issue(
                    session,
                    token_hash=token_hash,
                    purpose=purpose,
                    user_id=record.user_id,
                    email=record.email,
                    tenant_id=record.tenant_id,
                    created_at=record.created_at,
                    expires_at=record.expires_at,
                    meta=record.meta,
                )
                if otp_hash:
                    email_issue(
                        session,
                        token_hash=otp_hash,
                        purpose=purpose,
                        user_id=record.user_id,
                        email=record.email,
                        tenant_id=record.tenant_id,
                        created_at=record.created_at,
                        expires_at=record.expires_at,
                        meta={**base_meta, "peer_hash": token_hash} or None,
                    )
        else:
            with self._lock:
                self._path(token_hash).write_text(json.dumps(record.to_dict()), encoding="utf-8")
                if otp_hash:
                    otp_record = AuthEmailTokenRecord(
                        purpose=purpose,
                        user_id=user_id,
                        email=email_n,
                        tenant_id=tid,
                        created_at=now,
                        expires_at=record.expires_at,
                        meta={**base_meta, "peer_hash": token_hash} or None,
                    )
                    self._path(otp_hash).write_text(json.dumps(otp_record.to_dict()), encoding="utf-8")
        return IssuedAuthEmailToken(raw, otp)

    def peek(self, raw_token: str, purpose: TokenPurpose) -> AuthEmailTokenRecord | None:
        token_hash = _hash_token((raw_token or "").strip())
        if auth_tokens_use_postgres():
            from services.auth_token_pg_store import email_get

            with require_auth_token_pg_session() as session:
                row = email_get(session, token_hash)
                if row is None:
                    return None
                record = _row_to_record(row)
                if record.purpose != purpose or record.used_at is not None or time.time() > record.expires_at:
                    return None
                return record

        path = self._path(token_hash)
        with self._lock:
            if not path.exists():
                return None
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                record = AuthEmailTokenRecord.from_dict(data)
            except Exception:
                return None
            if record.purpose != purpose:
                return None
            if record.used_at is not None:
                return None
            if time.time() > record.expires_at:
                return None
            return record

    def _mark_peer_used(self, record: AuthEmailTokenRecord, used_at: float) -> None:
        peer = str((record.meta or {}).get("peer_hash") or "").strip()
        if not peer:
            return
        used = _with_used(record, used_at)
        if auth_tokens_use_postgres():
            from services.auth_token_pg_store import email_get, email_mark_used

            with require_auth_token_pg_session() as session:
                row = email_get(session, peer)
                if row is not None and row.used_at is None:
                    email_mark_used(session, row, used_at)
            return
        path = self._path(peer)
        with self._lock:
            if path.exists():
                path.write_text(json.dumps(used.to_dict()), encoding="utf-8")

    def consume(self, raw_token: str, purpose: TokenPurpose) -> AuthEmailTokenRecord | None:
        token_hash = _hash_token((raw_token or "").strip())
        if auth_tokens_use_postgres():
            from services.auth_token_pg_store import email_get, email_mark_used

            with require_auth_token_pg_session() as session:
                row = email_get(session, token_hash)
                if row is None:
                    return None
                record = _row_to_record(row)
                if record.purpose != purpose or record.used_at is not None or time.time() > record.expires_at:
                    return None
                now = time.time()
                email_mark_used(session, row, now)
            self._mark_peer_used(record, now)
            return _with_used(record, now)

        path = self._path(token_hash)
        with self._lock:
            if not path.exists():
                return None
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                record = AuthEmailTokenRecord.from_dict(data)
            except Exception:
                return None
            if record.purpose != purpose:
                return None
            if record.used_at is not None:
                return None
            if time.time() > record.expires_at:
                return None
            now = time.time()
            used = _with_used(record, now)
            path.write_text(json.dumps(used.to_dict()), encoding="utf-8")
        self._mark_peer_used(record, now)
        return used

    def consume_link_or_otp(
        self,
        token: str,
        purpose: TokenPurpose,
        email: str | None = None,
    ) -> AuthEmailTokenRecord | None:
        raw = (token or "").strip()
        if not raw:
            return None
        record = self.consume(raw, purpose)
        if record is not None:
            return record
        email_n = (email or "").strip().lower()
        if email_n and raw.isdigit() and len(raw) == 6:
            return self.consume(otp_secret(purpose, email_n, raw), purpose)
        return None

    def revoke_unused_for_user(self, user_id: str, purpose: TokenPurpose | None = None) -> int:
        if auth_tokens_use_postgres():
            from services.auth_token_pg_store import email_delete_unused_for_user

            with require_auth_token_pg_session() as session:
                return email_delete_unused_for_user(session, user_id, purpose)

        removed = 0
        with self._lock:
            for path in self._store_dir.glob("*.json"):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    if str(data.get("user_id")) != str(user_id):
                        continue
                    if purpose and data.get("purpose") != purpose:
                        continue
                    if data.get("used_at") is not None:
                        continue
                    path.unlink(missing_ok=True)
                    removed += 1
                except Exception:
                    continue
        return removed


auth_email_token_service = AuthEmailTokenService()
