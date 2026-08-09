"""Mobile bearer auth endpoints (access + refresh). No cookies/CSRF."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from modules.api_security import require_session
from modules.core import app
from services.dashboard_session_service import DEFAULT_SESSION_TTL_SECONDS, session_service
from services.mobile_refresh_token_service import mobile_refresh_token_service
from services.user_service import user_service


class MobileLoginRequest(BaseModel):
    email: str
    password: str


class MobileRefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=16)


def _issue_mobile_tokens(user: dict[str, Any]) -> dict[str, Any]:
    session = session_service.create_session(
        user_id=str(user["id"]),
        email=str(user.get("email") or ""),
        role=str(user.get("role") or "viewer"),
        permissions=user.get("permissions") if isinstance(user.get("permissions"), dict) else None,
        tenant_id=str(user.get("tenantId") or "linas"),
        password_epoch=int(user.get("passwordEpoch") or user.get("password_epoch") or 0),
    )
    access_token = session_service.cookie_value_for(session)
    refresh_token = mobile_refresh_token_service.issue(
        user_id=session.user_id,
        email=session.email,
        tenant_id=session.tenant_id,
        session_id=session.session_id,
    )
    return {
        "success": True,
        "user": session.to_public_user(),
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_in": DEFAULT_SESSION_TTL_SECONDS,
        "token_type": "Bearer",
    }


@app.post("/api/auth/mobile/login")
async def mobile_login(body: MobileLoginRequest) -> Any:
    email = (body.email or "").strip().lower()
    if not email or not body.password:
        raise HTTPException(status_code=400, detail="Email and password are required")
    user = user_service.authenticate(email, body.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if str(user.get("status") or "") != "active":
        raise HTTPException(status_code=403, detail="Account is not active")
    return _issue_mobile_tokens(user)


@app.post("/api/auth/mobile/refresh")
async def mobile_refresh(body: MobileRefreshRequest) -> Any:
    record = mobile_refresh_token_service.consume(body.refresh_token)
    if record is None:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    user = user_service.get_user_by_id(record.user_id)
    if user is None or str(user.get("status") or "") != "active":
        raise HTTPException(status_code=401, detail="User not available")
    # Revoke prior access session tied to this refresh (best-effort).
    try:
        session_service.revoke_session_id(record.session_id)
    except Exception:
        pass
    return _issue_mobile_tokens(user)


@app.post("/api/auth/mobile/logout")
async def mobile_logout(request: Request) -> Any:
    session = require_session(request)
    session_service.revoke_session_id(session.session_id)
    mobile_refresh_token_service.revoke_all_for_user(session.user_id)
    return {"success": True, "message": "Logged out"}
