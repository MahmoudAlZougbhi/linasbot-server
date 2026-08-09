"""Mobile integrations + usage read APIs."""

from __future__ import annotations

from typing import Any

from fastapi import Request

from modules.api_security import require_session
from modules.core import app
from services.credit_ledger_service import credit_ledger_service
from services.integration_capabilities import list_tenant_integration_status


def _without_comment_capabilities(integrations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Comments are not a mobile product surface — strip comment_* capability rows only."""
    out: list[dict[str, Any]] = []
    for row in integrations:
        caps = row.get("capabilities") or {}
        if isinstance(caps, dict):
            caps = {k: v for k, v in caps.items() if not str(k).lower().startswith("comment")}
        out.append({**row, "capabilities": caps})
    return out


@app.get("/api/mobile/integrations")
async def mobile_integrations(request: Request) -> Any:
    session = require_session(request)
    rows = list_tenant_integration_status(session.tenant_id)
    return {"success": True, "integrations": _without_comment_capabilities(rows)}


@app.get("/api/mobile/usage")
async def mobile_usage(request: Request) -> Any:
    session = require_session(request)
    credit_ledger_service.ensure_period_grant(session.tenant_id)
    return {
        "success": True,
        "credit_balance": credit_ledger_service.get_balance(session.tenant_id),
    }
