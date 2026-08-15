"""Web Chat store types and production wiring (PostgreSQL canonical SoT)."""

from __future__ import annotations

from typing import Any

from services.web_chat.config_models import WebChatWidgetConfig
from services.web_chat.store_file import WebChatFileStore, WebChatStore
from services.web_chat.store_pg import WebChatPgStore
from services.web_chat.store_types import WebChatMessage, WebChatVisitorSession

__all__ = [
    "WebChatFileStore",
    "WebChatMessage",
    "WebChatPgStore",
    "WebChatStore",
    "WebChatStoreBackend",
    "WebChatVisitorSession",
    "WebChatWidgetConfig",
    "web_chat_store",
]


class _LazyWebChatStore:
    """Defer PostgreSQL wiring until first use so imports stay safe in tests."""

    def __init__(self) -> None:
        self._delegate: WebChatPgStore | None = None

    def _resolve(self) -> WebChatPgStore:
        if self._delegate is None:
            self._delegate = WebChatPgStore()
        return self._delegate

    def __getattr__(self, item: str) -> Any:
        return getattr(self._resolve(), item)


WebChatStoreBackend = WebChatFileStore | WebChatPgStore | _LazyWebChatStore


web_chat_store: WebChatStoreBackend = _LazyWebChatStore()
