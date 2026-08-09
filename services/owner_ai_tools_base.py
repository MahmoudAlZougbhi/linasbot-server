"""Shared ToolResult for owner AI tools."""

from __future__ import annotations

from typing import Any


class ToolResult:
    __slots__ = (
        "ok",
        "name",
        "data",
        "requires_confirmation",
        "confirmation_token",
        "error",
    )

    def __init__(
        self,
        *,
        ok: bool,
        name: str,
        data: dict[str, Any],
        requires_confirmation: bool = False,
        confirmation_token: str | None = None,
        error: str | None = None,
    ) -> None:
        self.ok = ok
        self.name = name
        self.data = data
        self.requires_confirmation = requires_confirmation
        self.confirmation_token = confirmation_token
        self.error = error

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "name": self.name,
            "data": self.data,
            "requires_confirmation": self.requires_confirmation,
            "confirmation_token": self.confirmation_token,
            "error": self.error,
        }
