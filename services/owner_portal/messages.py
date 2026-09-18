"""Platform Owner message-flow inspection. Live Chat tenant inbox stays in live_chat."""

from __future__ import annotations

from typing import Any

from services.brain.turn_inspector import get_message_flow, list_message_flows


def list_platform_message_flows(*, tenant_id: str = "", limit: int = 50) -> list[dict[str, Any]]:
    return list_message_flows(tenant_id=(tenant_id or "").strip(), limit=limit)


def platform_message_flow(*, tenant_id: str, operation_id: str) -> dict[str, Any] | None:
    return get_message_flow(tenant_id=tenant_id, operation_id=operation_id)
