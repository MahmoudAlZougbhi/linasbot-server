"""OpenAI tools schema assembly (canonical utils.utils re-export)."""

from __future__ import annotations

from typing import Any

from utils.utils_tools_booking import OPENAI_BOOKING_TOOLS
from utils.utils_tools_lookup import OPENAI_LOOKUP_TOOLS


def get_openai_tools_schema(excluded_tool_names: Any | None = None) -> Any:
    """
    Returns the list of tools available to the OpenAI model in its required schema format.
    These definitions are based on LinasLaser AI Agent API Documentation.pdf.
    """
    tools: list[dict[str, Any]] = [*OPENAI_BOOKING_TOOLS, *OPENAI_LOOKUP_TOOLS]
    excluded = {str(name).strip() for name in (excluded_tool_names or []) if str(name).strip()}
    if excluded:
        tools = [tool for tool in tools if str((tool.get("function") or {}).get("name") or "").strip() not in excluded]
    return tools
