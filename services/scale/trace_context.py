"""ContextVar for the current inbound trace id (webhook → AI → send)."""

from __future__ import annotations

from contextvars import ContextVar

_TRACE_ID: ContextVar[str] = ContextVar("linas_trace_id", default="")


def set_trace_id(trace_id: str) -> None:
    _TRACE_ID.set(str(trace_id or "").strip())


def get_trace_id() -> str:
    return str(_TRACE_ID.get() or "").strip()
