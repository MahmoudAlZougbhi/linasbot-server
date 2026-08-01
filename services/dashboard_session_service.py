"""
Server-side dashboard sessions (HttpOnly cookie + Firestore/file-backed store).

Auth identity is never taken from client-supplied user_id alone.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from storage.persistent_storage import _DATA_ROOT

SESSION_COOKIE_NAME = "linas_session"
CSRF_COOKIE_NAME = "linas_csrf"
CSRF_HEADER_NAME = "X-CSRF-Token"

DEFAULT_SESSION_TTL_SECONDS = int(os.getenv("DASHBOARD_SESSION_TTL_SECONDS", str(12 * 60 * 60)))
SESSION_COLLECTION = "dashboard_sessions"


def _is_production() -> bool:
    env = (os.getenv("ENVIRONMENT") or os.getenv("ENV") or "").strip().lower()
    return env in {"prod", "production"}


def get_auth_secret() -> str:
    """
    Return the dashboard session signing secret.

    Production and ENVIRONMENT=test require an explicit secret (fail closed).
    Non-production local/dev may use a deterministic non-password fallback.
    Never generate a random secret per process restart.
    """
    secret = (os.getenv("DASHBOARD_AUTH_SECRET") or os.getenv("AUTH_SESSION_SECRET") or "").strip()
    if secret:
        return secret
    if _is_production() or (os.getenv("ENVIRONMENT") or "").strip().lower() == "test":
        raise RuntimeError(
            "DASHBOARD_AUTH_SECRET must be set (production/test fail closed; "
            "refusing insecure or restart-volatile signing secrets)"
        )
    # Deterministic local-dev fallback (not a password; never used in prod/test)
    return hashlib.sha256(b"linasbot-local-dev-session-secret").hexdigest()


def require_auth_secret_configured() -> None:
    """Raise RuntimeError if production/test cannot sign sessions safely."""
    get_auth_secret()


@dataclass
class SessionRecord:
    session_id: str
    user_id: str
    email: str
    role: str
    permissions: dict[str, bool] | None
    csrf_token: str
    created_at: float
    expires_at: float
    revoked: bool = False
    password_epoch: int = 0

    def to_public_user(self) -> dict[str, Any]:
        return {
            "id": self.user_id,
            "email": self.email,
            "role": self.role,
            "permissions": self.permissions,
            "status": "active",
        }


class DashboardSessionService:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._memory: dict[str, dict[str, Any]] = {}
        self._store_dir = Path(_DATA_ROOT) / "auth" / "sessions"
        self._store_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, session_id: str) -> Path:
        return self._store_dir / f"{session_id}.json"

    def _sign(self, session_id: str) -> str:
        digest = hmac.new(
            get_auth_secret().encode("utf-8"),
            session_id.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return f"{session_id}.{digest}"

    def parse_cookie_value(self, value: str | None) -> str | None:
        if not value or "." not in value:
            return None
        session_id, sig = value.rsplit(".", 1)
        if not session_id or not sig:
            return None
        expected = hmac.new(
            get_auth_secret().encode("utf-8"),
            session_id.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        return session_id

    def create_session(
        self,
        *,
        user_id: str,
        email: str,
        role: str,
        permissions: dict[str, bool] | None,
        password_epoch: int = 0,
        ttl_seconds: int | None = None,
    ) -> SessionRecord:
        ttl = int(ttl_seconds or DEFAULT_SESSION_TTL_SECONDS)
        now = time.time()
        record = SessionRecord(
            session_id=uuid.uuid4().hex,
            user_id=user_id,
            email=email,
            role=role or "viewer",
            permissions=permissions,
            csrf_token=secrets.token_urlsafe(32),
            created_at=now,
            expires_at=now + ttl,
            revoked=False,
            password_epoch=int(password_epoch or 0),
        )
        self._persist(record)
        return record

    def _persist(self, record: SessionRecord) -> None:
        payload: dict[str, Any] = {
            "session_id": record.session_id,
            "user_id": record.user_id,
            "email": record.email,
            "role": record.role,
            "permissions": record.permissions,
            "csrf_token": record.csrf_token,
            "created_at": record.created_at,
            "expires_at": record.expires_at,
            "revoked": record.revoked,
            "password_epoch": record.password_epoch,
        }
        with self._lock:
            self._memory[record.session_id] = payload
            path = self._path(record.session_id)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload), encoding="utf-8")
            tmp.replace(path)
        # Best-effort Firestore mirror for multi-instance hosts
        try:
            from utils.utils import get_firestore_db

            db = get_firestore_db()
            if db:
                db.collection("artifacts").document("linas-ai-bot-backend").collection(SESSION_COLLECTION).document(
                    record.session_id
                ).set(payload)
        except Exception:
            pass

    def _load(self, session_id: str) -> dict[str, Any] | None:
        with self._lock:
            if session_id in self._memory:
                return dict(self._memory[session_id])
            path = self._path(session_id)
            if path.exists():
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    self._memory[session_id] = data
                    return dict(data)
                except Exception:
                    return None
        try:
            from utils.utils import get_firestore_db

            db = get_firestore_db()
            if not db:
                return None
            snap = (
                db.collection("artifacts")
                .document("linas-ai-bot-backend")
                .collection(SESSION_COLLECTION)
                .document(session_id)
                .get()
            )
            if snap.exists:
                data = snap.to_dict() or {}
                with self._lock:
                    self._memory[session_id] = data
                return dict(data)
        except Exception:
            return None
        return None

    def get_valid_session(self, cookie_value: str | None) -> SessionRecord | None:
        session_id = self.parse_cookie_value(cookie_value)
        if not session_id:
            return None
        data = self._load(session_id)
        if not data:
            return None
        if data.get("revoked"):
            return None
        if float(data.get("expires_at") or 0) < time.time():
            return None
        session_epoch = int(data.get("password_epoch") or 0)
        user_id = str(data.get("user_id") or "")
        # Defense-in-depth: reject sessions whose password epoch no longer matches the user.
        if user_id:
            try:
                from services.user_service import user_service

                user = user_service.get_user_by_id(user_id)
                if user is not None:
                    current_epoch = int(user.get("passwordEpoch") or user.get("password_epoch") or 0)
                    if session_epoch != current_epoch:
                        return None
                    if str(user.get("status") or "") != "active":
                        return None
            except Exception:
                # If user lookup fails, rely on revoke/expiry only (do not invent access).
                pass
        return SessionRecord(
            session_id=str(data["session_id"]),
            user_id=user_id,
            email=str(data.get("email") or ""),
            role=str(data.get("role") or "viewer"),
            permissions=data.get("permissions"),
            csrf_token=str(data.get("csrf_token") or ""),
            created_at=float(data.get("created_at") or 0),
            expires_at=float(data.get("expires_at") or 0),
            revoked=bool(data.get("revoked")),
            password_epoch=session_epoch,
        )

    def revoke_session(self, cookie_value: str | None) -> None:
        session_id = self.parse_cookie_value(cookie_value)
        if not session_id:
            return
        data = self._load(session_id)
        if not data:
            return
        data["revoked"] = True
        record = SessionRecord(
            session_id=session_id,
            user_id=str(data.get("user_id") or ""),
            email=str(data.get("email") or ""),
            role=str(data.get("role") or "viewer"),
            permissions=data.get("permissions"),
            csrf_token=str(data.get("csrf_token") or ""),
            created_at=float(data.get("created_at") or 0),
            expires_at=float(data.get("expires_at") or 0),
            revoked=True,
            password_epoch=int(data.get("password_epoch") or 0),
        )
        self._persist(record)

    def revoke_all_for_user(self, user_id: str) -> int:
        """Revoke every session for user_id locally and in Firestore (multi-instance)."""
        count = 0
        touched: dict[str, dict[str, Any]] = {}
        with self._lock:
            ids = list(self._memory.keys())
            for sid in ids:
                data = self._memory.get(sid) or {}
                if str(data.get("user_id")) == str(user_id):
                    data["revoked"] = True
                    self._memory[sid] = data
                    path = self._path(sid)
                    path.write_text(json.dumps(data), encoding="utf-8")
                    touched[sid] = data
                    count += 1
            for path in self._store_dir.glob("*.json"):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    continue
                if str(data.get("user_id")) == str(user_id) and not data.get("revoked"):
                    data["revoked"] = True
                    path.write_text(json.dumps(data), encoding="utf-8")
                    sid = str(data.get("session_id") or path.stem)
                    self._memory[sid] = data
                    touched[sid] = data
                    count += 1
        # Mirror revoke across instances via Firestore query on user_id
        try:
            from utils.utils import get_firestore_db

            db = get_firestore_db()
            if db:
                coll = db.collection("artifacts").document("linas-ai-bot-backend").collection(SESSION_COLLECTION)
                snaps = list(coll.where("user_id", "==", str(user_id)).stream())
                for snap in snaps:
                    data = snap.to_dict() or {}
                    if data.get("revoked"):
                        continue
                    data["revoked"] = True
                    snap.reference.set(data)
                    sid = str(data.get("session_id") or snap.id)
                    with self._lock:
                        self._memory[sid] = data
                        self._path(sid).write_text(json.dumps(data), encoding="utf-8")
                    if sid not in touched:
                        count += 1
                    touched[sid] = data
        except Exception:
            pass
        return count

    def cookie_value_for(self, record: SessionRecord) -> str:
        return self._sign(record.session_id)


session_service = DashboardSessionService()
