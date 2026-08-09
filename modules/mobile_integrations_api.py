"""Mobile integrations + usage read APIs."""

from __future__ import annotations

from typing import Any

from fastapi import Request

from modules.api_security import require_session
from modules.core import app
from services.credit_ledger_service import credit_ledger_service
from services.integration_capabilities import list_tenant_integration_status


@app.get("/api/mobile/integrations")
async def mobile_integrations(request: Request) -> Any:
    session = require_session(request)
    return {"success": True, "integrations": list_tenant_integration_status(session.tenant_id)}


@app.get("/api/mobile/usage")
async def mobile_usage(request: Request) -> Any:
    session = require_session(request)
    credit_ledger_service.ensure_period_grant(session.tenant_id)
    return {
        "success": True,
        "credit_balance": credit_ledger_service.get_balance(session.tenant_id),
    }
