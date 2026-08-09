"""Owner Linas AI conversation persistence (separate from social customer chats)."""

from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from storage.persistent_storage import _DATA_ROOT


@dataclass
class OwnerChatMessage:
    id: str
    role: str  # user | assistant | system
    content: str
    created_at: float
    tool_calls: list[dict[str, Any]] | None = None


@dataclass
class OwnerConversation:
    id: str
    tenant_id: str
    user_id: str
    title: str
    created_at: float
    updated_at: float
    archived: bool = False
    deleted: bool = False
    messages: list[OwnerChatMessage] | None = None


class OwnerChatStore:
    def __init__(self, root: Path | None = None) -> None:
        self._lock = threading.RLock()
        self._root = root or (Path(_DATA_ROOT) / "owner_chat")
        self._root.mkdir(parents=True, exist_ok=True)

    def _tenant_dir(self, tenant_id: str) -> Path:
        path = self._root / tenant_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _conv_path(self, tenant_id: str, conversation_id: str) -> Path:
        return self._tenant_dir(tenant_id) / f"{conversation_id}.json"

    def create_conversation(
        self,
        *,
        tenant_id: str,
        user_id: str,
        title: str = "New chat",
        greeting_text: str | None = None,
    ) -> OwnerConversation:
        now = time.time()
        if greeting_text is None:
            try:
                from services.owner_ai_greeting import build_greeting

                greeting_text = build_greeting(tenant_id=tenant_id, user_id=user_id)["text"]
            except Exception:
                greeting_text = (
                    "Hello. I’m Linas AI — your System Copilot for the whole app. "
                    "Content Management is one capability; ask about integrations, usage, or creative work too."
                )
        conv = OwnerConversation(
            id=uuid.uuid4().hex,
            tenant_id=tenant_id,
            user_id=user_id,
            title=(title or "New chat")[:120],
            created_at=now,
            updated_at=now,
            messages=[
                OwnerChatMessage(
                    id=uuid.uuid4().hex,
                    role="assistant",
                    content=str(greeting_text),
                    created_at=now,
                )
            ],
        )
        self._write(conv)
        return conv

    def list_conversations(self, *, tenant_id: str, user_id: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        with self._lock:
            for path in self._tenant_dir(tenant_id).glob("*.json"):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    continue
                if str(data.get("user_id")) != user_id:
                    continue
                if data.get("deleted"):
                    continue
                items.append(
                    {
                        "id": data["id"],
                        "title": data.get("title") or "Chat",
                        "created_at": data.get("created_at"),
                        "updated_at": data.get("updated_at"),
                        "archived": bool(data.get("archived")),
                    }
                )
        items.sort(key=lambda x: float(x.get("updated_at") or 0), reverse=True)
        return items

    def get_conversation(self, *, tenant_id: str, user_id: str, conversation_id: str) -> OwnerConversation | None:
        path = self._conv_path(tenant_id, conversation_id)
        with self._lock:
            if not path.is_file():
                return None
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                return None
        if str(data.get("tenant_id")) != tenant_id or str(data.get("user_id")) != user_id:
            return None
        if data.get("deleted"):
            return None
        messages = [
            OwnerChatMessage(
                id=str(m.get("id") or uuid.uuid4().hex),
                role=str(m.get("role") or "assistant"),
                content=str(m.get("content") or ""),
                created_at=float(m.get("created_at") or 0),
                tool_calls=m.get("tool_calls") if isinstance(m.get("tool_calls"), list) else None,
            )
            for m in (data.get("messages") or [])
            if isinstance(m, dict)
        ]
        return OwnerConversation(
            id=str(data["id"]),
            tenant_id=tenant_id,
            user_id=user_id,
            title=str(data.get("title") or "Chat"),
            created_at=float(data.get("created_at") or 0),
            updated_at=float(data.get("updated_at") or 0),
            archived=bool(data.get("archived")),
            deleted=False,
            messages=messages,
        )

    def append_message(
        self,
        *,
        tenant_id: str,
        user_id: str,
        conversation_id: str,
        role: str,
        content: str,
        tool_calls: list[dict[str, Any]] | None = None,
    ) -> OwnerChatMessage | None:
        conv = self.get_conversation(tenant_id=tenant_id, user_id=user_id, conversation_id=conversation_id)
        if conv is None:
            return None
        msg = OwnerChatMessage(
            id=uuid.uuid4().hex,
            role=role,
            content=content,
            created_at=time.time(),
            tool_calls=tool_calls,
        )
        msgs = list(conv.messages or [])
        msgs.append(msg)
        conv.messages = msgs
        conv.updated_at = msg.created_at
        if role == "user" and (conv.title == "New chat" or not conv.title):
            conv.title = content.strip()[:60] or "New chat"
        self._write(conv)
        return msg

    def rename(self, *, tenant_id: str, user_id: str, conversation_id: str, title: str) -> bool:
        conv = self.get_conversation(tenant_id=tenant_id, user_id=user_id, conversation_id=conversation_id)
        if conv is None:
            return False
        conv.title = title.strip()[:120] or conv.title
        conv.updated_at = time.time()
        self._write(conv)
        return True

    def soft_delete(self, *, tenant_id: str, user_id: str, conversation_id: str) -> bool:
        conv = self.get_conversation(tenant_id=tenant_id, user_id=user_id, conversation_id=conversation_id)
        if conv is None:
            return False
        conv.deleted = True
        conv.updated_at = time.time()
        self._write(conv)
        return True

    def _write(self, conv: OwnerConversation) -> None:
        payload = {
            "id": conv.id,
            "tenant_id": conv.tenant_id,
            "user_id": conv.user_id,
            "title": conv.title,
            "created_at": conv.created_at,
            "updated_at": conv.updated_at,
            "archived": conv.archived,
            "deleted": conv.deleted,
            "messages": [asdict(m) for m in (conv.messages or [])],
        }
        path = self._conv_path(conv.tenant_id, conv.id)
        with self._lock:
            path.write_text(json.dumps(payload), encoding="utf-8")


owner_chat_store = OwnerChatStore()
