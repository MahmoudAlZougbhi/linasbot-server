"""Typed, authorized tools for the owner Linas AI assistant.

LLM output never writes storage directly — tools call service APIs only.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from modules.api_security import resolve_permissions


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


def _require(role: str, permission: str) -> None:
    if not resolve_permissions(role, None).get(permission):
        raise PermissionError(f"Missing permission: {permission}")


async def tool_read_cm(*, tenant_id: str, role: str, section: str | None = None) -> ToolResult:
    _require(role, "contentManagers")
    from services.cm.constants import CM_SECTIONS
    from services.cm.storage import UnknownSectionError, get_draft

    if section:
        try:
            env = get_draft(section, tenant_id=tenant_id, create_default=False)
        except UnknownSectionError:
            return ToolResult(ok=False, name="read_cm", data={}, error=f"Unknown section: {section}")
        payload = env.model_dump(mode="json") if env is not None else None
        return ToolResult(ok=True, name="read_cm", data={"section": section, "draft": payload})
    from services.cm.storage import list_sections

    listed = {str(item.get("section")): item for item in list_sections(tenant_id=tenant_id)}
    overview: dict[str, Any] = {}
    for sec in CM_SECTIONS:
        item = listed.get(sec)
        overview[sec] = {
            "present": bool(item and item.get("exists")),
            "revision": item.get("revision") if item else None,
        }
    return ToolResult(ok=True, name="read_cm", data={"sections": overview})


async def tool_validate_cm(*, tenant_id: str, role: str) -> ToolResult:
    _require(role, "contentManagers")
    from services.cm.validation import validate_cm

    report = validate_cm(tenant_id=tenant_id)
    return ToolResult(ok=True, name="validate_cm", data={"report": report})


async def tool_publish_cm(*, tenant_id: str, role: str, confirmed: bool) -> ToolResult:
    _require(role, "contentPublish")
    if not confirmed:
        return ToolResult(
            ok=True,
            name="publish_cm",
            data={"action": "publish_cm"},
            requires_confirmation=True,
            confirmation_token="publish_cm",
            error="Confirmation required before publish",
        )
    from services.cm.publish import publish_draft

    result = await publish_draft(tenant_id=tenant_id)
    data = result if isinstance(result, dict) else {"result": str(result)}
    return ToolResult(ok=True, name="publish_cm", data=data)


async def tool_read_usage(*, tenant_id: str, role: str) -> ToolResult:
    from services.token_wallet_service import token_wallet_service

    wallet = token_wallet_service.get_wallet(tenant_id)
    return ToolResult(ok=True, name="read_usage", data={"wallet": wallet.to_public_dict()})


async def tool_read_subscription(*, tenant_id: str, role: str) -> ToolResult:
    from services.entitlements_service import get_tenant_entitlement_public

    return ToolResult(ok=True, name="read_subscription", data=get_tenant_entitlement_public(tenant_id))


async def tool_read_integrations(*, tenant_id: str, role: str) -> ToolResult:
    from services.integration_capabilities import list_tenant_integration_status

    return ToolResult(
        ok=True,
        name="read_integrations",
        data={"integrations": list_tenant_integration_status(tenant_id)},
    )


TOOL_HANDLERS: dict[str, Callable[..., Awaitable[ToolResult]]] = {
    "read_cm": tool_read_cm,
    "validate_cm": tool_validate_cm,
    "publish_cm": tool_publish_cm,
    "read_usage": tool_read_usage,
    "read_subscription": tool_read_subscription,
    "read_integrations": tool_read_integrations,
}


def list_tool_names() -> list[str]:
    return sorted(TOOL_HANDLERS.keys())
