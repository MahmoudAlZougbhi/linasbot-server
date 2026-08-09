"""Evidence-based Instagram/Facebook health diagnosis (read-only)."""

from __future__ import annotations

from typing import Any

from services.owner_ai_tools_base import ToolResult


async def tool_diagnose_meta_health(
    *,
    tenant_id: str,
    role: str,
    channel: str = "all",
) -> ToolResult:
    """Consolidate connection + capability readiness without Meta mutations."""
    del role  # RBAC enforced by dispatcher
    from services.owner_copilot_v2.flags import owner_copilot_meta_actions_enabled

    if owner_copilot_meta_actions_enabled():
        # Even if flag is on, this tool remains read-only by design.
        pass

    integrations: dict[str, Any] = {}
    try:
        from services.owner_ai_tools_read import tool_read_integrations

        integ = await tool_read_integrations(tenant_id=tenant_id, role="owner")
        integrations = integ.data if integ.ok else {"error": integ.error}
    except Exception as exc:  # noqa: BLE001
        integrations = {"error": type(exc).__name__}

    ch = (channel or "all").lower()
    findings: list[dict[str, Any]] = []
    connected = bool(
        (integrations or {}).get("any_connected") or (integrations.get("integrations") or {}).get("any_connected")
    )
    if not connected:
        findings.append(
            {
                "severity": "connection",
                "status": "not_connected",
                "evidence": "integrations.any_connected=false",
                "remediation": "Open Integrations and connect Instagram/Facebook (App A). No token reset performed.",
            }
        )
    else:
        findings.append(
            {
                "severity": "connection",
                "status": "connected",
                "evidence": "integrations snapshot reports a connected asset",
                "remediation": None,
            }
        )

    # Capability honesty from knowledge registry patterns
    findings.append(
        {
            "severity": "comments",
            "status": "partial_or_gated",
            "evidence": "comment_read/reply require App Review + live_verified; not mutated by this tool",
            "remediation": "Verify App Review + live_verified in Integrations; do not disconnect/reconnect from chat.",
        }
    )
    findings.append(
        {
            "severity": "dms",
            "status": "check_runtime",
            "evidence": "Use get_recent_customer_interactions / TRACE for delivery failures",
            "remediation": "If DMs fail, inspect recent TRACE ids rather than resetting tokens.",
        }
    )

    summary = (
        "Instagram/Facebook diagnosis is read-only. "
        + ("No Meta assets connected." if not connected else "At least one Meta asset appears connected.")
        + " Creative publishing is out of product scope for V2."
    )
    data = {
        "channel": ch,
        "summary": summary,
        "findings": findings,
        "integrations": integrations,
        "meta_mutations": False,
        "app": "A",
    }
    return ToolResult(ok=True, name="diagnose_meta_health", data=data)
