"""File-backed guest chat sessions keyed by client guest_session_id."""

from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from services.guest_chat_limits import GUEST_MAX_QUESTIONS
from storage.persistent_storage import _DATA_ROOT


@dataclass
class GuestMessage:
    id: str
    role: str
    content: str
    created_at: float


@dataclass
class GuestSession:
    id: str
    created_at: float
    updated_at: float
    questions_used: int = 0
    messages: list[GuestMessage] = field(default_factory=list)

    def remaining(self) -> int:
        return max(0, GUEST_MAX_QUESTIONS - self.questions_used)


class GuestChatStore:
    def __init__(self, root: Path | None = None) -> None:
        self._lock = threading.RLock()
        self._root = root or (Path(_DATA_ROOT) / "guest_chat")
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, session_id: str) -> Path:
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in session_id)[:80]
        return self._root / f"{safe}.json"

    def _load(self, session_id: str) -> GuestSession | None:
        path = self._path(session_id)
        if not path.exists():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        msgs = [
            GuestMessage(
                id=str(m.get("id") or uuid.uuid4().hex),
                role=str(m.get("role") or "assistant"),
                content=str(m.get("content") or ""),
                created_at=float(m.get("created_at") or time.time()),
            )
            for m in (raw.get("messages") or [])
            if isinstance(m, dict)
        ]
        return GuestSession(
            id=str(raw.get("id") or session_id),
            created_at=float(raw.get("created_at") or time.time()),
            updated_at=float(raw.get("updated_at") or time.time()),
            questions_used=int(raw.get("questions_used") or 0),
            messages=msgs,
        )

    def _save(self, session: GuestSession) -> None:
        payload: dict[str, Any] = {
            "id": session.id,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
            "questions_used": session.questions_used,
            "messages": [asdict(m) for m in session.messages],
        }
        self._path(session.id).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def get_or_create(self, session_id: str, *, greeting: str) -> GuestSession:
        sid = (session_id or "").strip()
        if not sid or len(sid) < 8 or len(sid) > 80:
            raise ValueError("invalid guest_session_id")
        with self._lock:
            existing = self._load(sid)
            if existing is not None:
                return existing
            now = time.time()
            session = GuestSession(
                id=sid,
                created_at=now,
                updated_at=now,
                questions_used=0,
                messages=[
                    GuestMessage(
                        id=uuid.uuid4().hex,
                        role="assistant",
                        content=greeting,
                        created_at=now,
                    )
                ],
            )
            self._save(session)
            return session

    def get(self, session_id: str) -> GuestSession | None:
        with self._lock:
            return self._load(session_id)

    def append_turn(
        self,
        session_id: str,
        *,
        user_text: str,
        assistant_text: str,
    ) -> GuestSession:
        with self._lock:
            session = self._load(session_id)
            if session is None:
                raise KeyError("session not found")
            now = time.time()
            session.messages.append(
                GuestMessage(id=uuid.uuid4().hex, role="user", content=user_text, created_at=now)
            )
            session.messages.append(
                GuestMessage(
                    id=uuid.uuid4().hex,
                    role="assistant",
                    content=assistant_text,
                    created_at=now + 0.001,
                )
            )
            session.questions_used += 1
            session.updated_at = now
            self._save(session)
            return session


guest_chat_store = GuestChatStore()
