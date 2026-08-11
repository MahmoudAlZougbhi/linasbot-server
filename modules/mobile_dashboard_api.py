"""Tenant mobile Dashboard API — composed read model."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Query, Request

from modules.api_security import require_permission
from modules.core import app
from services.tenant_mobile_dashboard.compose import build_tenant_mobile_dashboard
from services.tenant_mobile_dashboard.periods import PeriodValidationError, TimezoneValidationError


@app.get("/api/mobile/dashboard")
async def mobile_dashboard(
    request: Request,
    period: str = Query(default="billing"),
    timezone: str = Query(default="UTC", alias="tz"),
) -> Any:
    """Bearer-authenticated tenant Dashboard aggregate.

    Tenant is derived only from the authenticated session — never from client body.
    """
    session = require_permission(request, "dashboard")
    try:
        payload = build_tenant_mobile_dashboard(
            tenant_id=session.tenant_id,
            user_id=session.user_id,
            period_raw=period,
            timezone_raw=timezone,
        )
    except PeriodValidationError as exc:
        raise HTTPException(status_code=400, detail={"code": exc.code, "message": str(exc)}) from exc
    except TimezoneValidationError as exc:
        raise HTTPException(status_code=400, detail={"code": exc.code, "message": str(exc)}) from exc
    return payload
