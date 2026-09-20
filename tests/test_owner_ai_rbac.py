"""S2/S3: /api/owner-ai and sensitive Sol read tools use contentManagers."""

from __future__ import annotations

import pytest

from modules.api_security import required_permission_for, resolve_permissions
from services.owner_copilot.tools_read import (
    tool_read_integrations,
    tool_read_profile,
    tool_read_subscription,
    tool_read_usage,
)


def test_owner_ai_http_maps_to_content_managers() -> None:
    assert required_permission_for("GET", "/api/owner-ai/conversations") == "contentManagers"
    assert required_permission_for("POST", "/api/owner-ai/conversations/c1/messages") == "contentManagers"
    assert required_permission_for("POST", "/api/owner-ai/conversations/c1/messages/stream") == "contentManagers"


def test_operator_lacks_content_managers() -> None:
    perms = resolve_permissions("operator", None)
    assert perms["contentManagers"] is False
    assert perms["settings"] is False


@pytest.mark.asyncio
async def test_sensitive_read_tools_denied_for_operator() -> None:
    with pytest.raises(PermissionError):
        await tool_read_usage(tenant_id="t1", role="operator")
    with pytest.raises(PermissionError):
        await tool_read_subscription(tenant_id="t1", role="operator")
    with pytest.raises(PermissionError):
        await tool_read_integrations(tenant_id="t1", role="operator")


@pytest.mark.asyncio
async def test_profile_stays_lighter_without_content_managers() -> None:
    result = await tool_read_profile(tenant_id="t1", role="operator", user_id="missing-user")
    assert result.ok is True
