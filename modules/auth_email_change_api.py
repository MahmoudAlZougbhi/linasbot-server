"""Email-change + security notification routes (split from auth_api for LOC)."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import Request
from pydantic import BaseModel

from modules.api_security import require_session
from modules.auth_api_common import AUTH_LOGIN_TIMEOUT_SECONDS
from modules.core import app
from services.auth_email_tokens import EMAIL_CHANGE_TTL_SECONDS, auth_email_token_service
from services.dashboard_session_service import session_service
from services.email_dispatch import (
    send_email_change_confirm,
    send_email_changed_notice,
    send_password_changed_email,
)
from services.mail_service import mail_configured
from services.user_service import user_service


class RequestEmailChangeRequest(BaseModel):
    new_email: str
    current_password: str


class ConfirmEmailChangeRequest(BaseModel):
    token: str


@app.post("/api/auth/request-email-change")
async def request_email_change(body: RequestEmailChangeRequest, request: Request) -> Any:
    """Re-auth with password, then send confirm link to the new address + notice later."""
    session = require_session(request)
    new_email = (body.new_email or "").strip().lower()
    if not new_email or "@" not in new_email:
        return {"success": False, "error": "Valid new email is required"}

    user = user_service.get_user_by_id(session.user_id)
    if not user or user.get("status") != "active":
        return {"success": False, "error": "User not found"}

    # Re-authenticate before sensitive change.
    try:
        authed = await asyncio.wait_for(
            asyncio.to_thread(
                user_service.authenticate,
                str(user.get("email") or ""),
                body.current_password or "",
            ),
            timeout=AUTH_LOGIN_TIMEOUT_SECONDS,
        )
    except Exception:
        return {"success": False, "error": "Re-authentication failed"}
    if not authed or str(authed.get("id")) != str(session.user_id):
        return {"success": False, "error": "Current password is incorrect"}

    if new_email == str(user.get("email") or "").strip().lower():
        return {"success": False, "error": "New email must be different"}

    existing = user_service.get_user_by_email(new_email)
    if existing and str(existing.get("id")) != str(session.user_id):
        # Anti-enumeration: same generic message as success path for occupied addresses.
        return {
            "success": True,
            "message": "If the address can be used, a confirmation email has been sent.",
            "mail_configured": mail_configured(),
        }

    tenant_id = str(user.get("tenantId") or session.tenant_id or "").strip()
    if not tenant_id:
        return {"success": False, "error": "Tenant required"}

    auth_email_token_service.revoke_unused_for_user(str(user["id"]), "email_change")
    raw = auth_email_token_service.issue(
        purpose="email_change",
        user_id=str(user["id"]),
        email=new_email,
        tenant_id=tenant_id,
        ttl_seconds=EMAIL_CHANGE_TTL_SECONDS,
        meta={"previous_email": str(user.get("email") or "").strip().lower()},
    )
    locale = str(user.get("preferredLanguage") or "en")
    result = send_email_change_confirm(
        to_email=new_email,
        raw_token=raw,
        locale=locale,
        user_id=str(user["id"]),
    )
    return {
        "success": True,
        "message": "If the address can be used, a confirmation email has been sent.",
        "mail_configured": mail_configured(),
        "mail_sent": bool(result.sent),
    }


@app.post("/api/auth/confirm-email-change")
async def confirm_email_change(body: ConfirmEmailChangeRequest, request: Request) -> Any:
    token = (body.token or "").strip()
    if not token:
        return {"success": False, "error": "Token is required"}
    record = auth_email_token_service.consume(token, "email_change")
    if record is None:
        return {"success": False, "error": "Invalid or expired confirmation link"}

    previous = ""
    if isinstance(record.meta, dict):
        previous = str(record.meta.get("previous_email") or "").strip().lower()

    try:
        user = await asyncio.wait_for(
            asyncio.to_thread(user_service.change_email_address, record.user_id, record.email),
            timeout=AUTH_LOGIN_TIMEOUT_SECONDS,
        )
    except ValueError as exc:
        return {"success": False, "error": str(exc)}
    except Exception:
        return {"success": False, "error": "Failed to change email"}

    session_service.revoke_all_for_user(record.user_id)
    locale = str((user or {}).get("preferredLanguage") or "en")
    if previous and previous != record.email:
        send_email_changed_notice(to_email=previous, locale=locale, user_id=record.user_id)
    return {"success": True, "message": "Email updated. Please sign in again.", "user": user}


def notify_password_changed(*, user_id: str, email: str, locale: str | None = None) -> None:
    """Best-effort security email after password change/reset (never raises to callers)."""
    try:
        send_password_changed_email(to_email=email, locale=locale, user_id=user_id)
    except Exception:
        return
