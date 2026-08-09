"""Opaque mobile refresh tokens (file-backed; hash-only at rest)."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from storage.persistent_storage import _DATA_ROOT

MOBILE_REFRESH_TTL_SECONDS = int(os.getenv("MOBILE_REFRESH_TTL_SECONDS", str(60 * 60 * 24 * 30)))


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class MobileRefreshRecord:
    user_id: str
    email: str
    tenant_id: str
    session_id: str
    created_at: float
    expires_at: float
    revoked_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "email": self.email,
            "tenant_id": self.tenant_id,
            "session_id": self.session_id,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "revoked_at": self.revoked_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MobileRefreshRecord:
        return cls(
            user_id=str(data["user_id"]),
            email=str(data.get("email") or ""),
            tenant_id=str(data.get("tenant_id") or "linas"),
            session_id=str(data.get("session_id") or ""),
            created_at=float(data["created_at"]),
            expires_at=float(data["expires_at"]),
            revoked_at=float(data["revoked_at"]) if data.get("revoked_at") is not None else None,
        )


class MobileRefreshTokenService:
    def __init__(self, store_dir: Path | None = None) -> None:
        self._lock = threading.RLock()
        self._store_dir = store_dir or (Path(_DATA_ROOT) / "auth" / "mobile_refresh")
        self._store_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, token_hash: str) -> Path:
        return self._store_dir / f"{token_hash}.json"

    def issue(
        self,
        *,
        user_id: str,
        email: str,
        tenant_id: str,
        session_id: str,
        ttl_seconds: int | None = None,
    ) -> str:
        raw = secrets.token_urlsafe(48)
        token_hash = _hash_token(raw)
        now = time.time()
        ttl = max(300, int(ttl_seconds or MOBILE_REFRESH_TTL_SECONDS))
        record = MobileRefreshRecord(
            user_id=user_id,
            email=(email or "").strip().lower(),
            tenant_id=tenant_id,
            session_id=session_id,
            created_at=now,
            expires_at=now + ttl,
        )
        with self._lock:
            self._path(token_hash).write_text(json.dumps(record.to_dict()), encoding="utf-8")
        return raw

    def consume(self, raw: str) -> MobileRefreshRecord | None:
        """Validate and revoke refresh token (rotate-on-use)."""
        token_hash = _hash_token((raw or "").strip())
        path = self._path(token_hash)
        with self._lock:
            if not path.is_file():
                return None
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                return None
            record = MobileRefreshRecord.from_dict(data)
            if record.revoked_at is not None:
                return None
            if record.expires_at < time.time():
                path.unlink(missing_ok=True)
                return None
            revoked = MobileRefreshRecord(
                user_id=record.user_id,
                email=record.email,
                tenant_id=record.tenant_id,
                session_id=record.session_id,
                created_at=record.created_at,
                expires_at=record.expires_at,
                revoked_at=time.time(),
            )
            path.write_text(json.dumps(revoked.to_dict()), encoding="utf-8")
            return record

    def revoke_all_for_user(self, user_id: str) -> int:
        count = 0
        with self._lock:
            for path in self._store_dir.glob("*.json"):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    continue
                if str(data.get("user_id") or "") != user_id:
                    continue
                if data.get("revoked_at") is not None:
                    continue
                data["revoked_at"] = time.time()
                path.write_text(json.dumps(data), encoding="utf-8")
                count += 1
        return count


mobile_refresh_token_service = MobileRefreshTokenService()
