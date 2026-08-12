"""Password-reset and email-verification token store (file-backed under data root).

Tokens are single-use, time-limited, and stored as SHA-256 hashes — raw tokens
never persist. CSRF is not required for public token redeem endpoints; rate
limits apply at the API layer.
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

from storage.persistent_storage import _DATA_ROOT

TokenPurpose = Literal["password_reset", "email_verify", "email_change"]

PASSWORD_RESET_TTL_SECONDS = int(os.getenv("PASSWORD_RESET_TTL_SECONDS", str(60 * 60)))
EMAIL_VERIFY_TTL_SECONDS = int(os.getenv("EMAIL_VERIFY_TTL_SECONDS", str(48 * 60 * 60)))
EMAIL_CHANGE_TTL_SECONDS = int(os.getenv("EMAIL_CHANGE_TTL_SECONDS", str(24 * 60 * 60)))


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


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
    ) -> str:
        """Create a token and return the raw secret (show once to the user via email)."""
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
        record = AuthEmailTokenRecord(
            purpose=purpose,
            user_id=user_id,
            email=(email or "").strip().lower(),
            tenant_id=tid,
            created_at=now,
            expires_at=now + max(60, int(ttl_seconds)),
            meta=dict(meta) if isinstance(meta, dict) else None,
        )
        with self._lock:
            self._path(token_hash).write_text(json.dumps(record.to_dict()), encoding="utf-8")
        return raw

    def peek(self, raw_token: str, purpose: TokenPurpose) -> AuthEmailTokenRecord | None:
        token_hash = _hash_token((raw_token or "").strip())
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

    def consume(self, raw_token: str, purpose: TokenPurpose) -> AuthEmailTokenRecord | None:
        """Validate and mark token used. Returns None if invalid/expired/already used."""
        token_hash = _hash_token((raw_token or "").strip())
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
            used = AuthEmailTokenRecord(
                purpose=record.purpose,
                user_id=record.user_id,
                email=record.email,
                tenant_id=record.tenant_id,
                created_at=record.created_at,
                expires_at=record.expires_at,
                used_at=time.time(),
                meta=record.meta,
            )
            path.write_text(json.dumps(used.to_dict()), encoding="utf-8")
            return used

    def revoke_unused_for_user(self, user_id: str, purpose: TokenPurpose | None = None) -> int:
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
