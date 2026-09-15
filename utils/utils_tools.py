"""OpenAI tools schema assembly (canonical utils.utils re-export)."""

from __future__ import annotations

from typing import Any


def get_openai_tools_schema(excluded_tool_names: Any | None = None) -> Any:
    """Empty: clinic booking/CRM tool schemas are not wired to live Brain."""
    del excluded_tool_names
    return []
