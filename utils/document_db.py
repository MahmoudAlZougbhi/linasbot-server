"""Postgres document client used where the app used to open a Firestore client."""

from __future__ import annotations

from typing import Any

_client: Any = None
_ready = False


def initialize_document_db() -> Any:
    """Open the Postgres document store once. Missing database config leaves it unset."""
    global _client, _ready
    if _ready:
        return _client
    _ready = True
    try:
        from services.persistence.document_store import open_document_client

        _client = open_document_client()
    except Exception as exc:
        print(f"[documents] store unavailable: {type(exc).__name__}")
        _client = None
    return _client


def get_document_db() -> Any:
    if not _ready:
        initialize_document_db()
    return _client
