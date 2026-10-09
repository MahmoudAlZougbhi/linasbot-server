"""Stop any send whose target is a sandbox id."""

from __future__ import annotations

import contextvars
from collections.abc import Iterator
from contextlib import contextmanager

_ACTIVE: contextvars.ContextVar[bool] = contextvars.ContextVar("sandbox_active", default=False)


class SandboxOutboundBlocked(RuntimeError):
    def __init__(self, target: str) -> None:
        super().__init__("sandbox_outbound_blocked")
        self.target = target


@contextmanager
def sandbox_scope() -> Iterator[None]:
    token = _ACTIVE.set(True)
    try:
        yield
    finally:
        _ACTIVE.reset(token)


def sandbox_active() -> bool:
    return bool(_ACTIVE.get())


def refuse_sandbox_target(target: str) -> None:
    text = str(target or "").lstrip("/")
    head = text.split("/", 1)[0]
    if sandbox_active() or head.startswith("sbx_"):
        raise SandboxOutboundBlocked(head or text)
