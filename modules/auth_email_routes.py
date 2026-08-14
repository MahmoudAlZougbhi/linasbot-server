"""Public forgot / reset / verify-email routes (LOC split from auth_api)."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import Request, Response

from modules.auth_api_common import (
    AUTH_LOGIN_TIMEOUT_SECONDS,
    ForgotPasswordRequest,
    ResendVerificationRequest,
    ResetPasswordRequest,
    VerifyEmailRequest,
    _clear_auth_cookies,
)
from modules.core import app
from services.dashboard_session_service import SESSION_COOKIE_NAME, session_service
from services.user_service import user_service


@app.post("/api/auth/forgot-password")
async def forgot_password(body: ForgotPasswordRequest) -> Any:
    """
    Always return a generic success message (do not reveal whether email exists).
    When mail is configured, send a time-limited reset link plus a 6-digit code.
    """
    from services.auth_email_tokens import auth_email_token_service
    from services.email_dispatch import send_reset_password_email
    from services.mail_service import mail_configured

    email = (body.email or "").strip().lower()
    generic = {
        "success": True,
        "message": "If an account exists for that email, a password reset link has been sent.",
        "mail_configured": mail_configured(),
    }
    if not email or "@" not in email:
        return generic

    try:
        user = await asyncio.wait_for(
            asyncio.to_thread(user_service.get_user_by_email, email),
            timeout=AUTH_LOGIN_TIMEOUT_SECONDS,
        )
    except Exception:
        return generic

    if not user or user.get("status") != "active":
        return generic

    tenant_id = str(user.get("tenantId") or "").strip()
    if not tenant_id:
        return generic

    auth_email_token_service.revoke_unused_for_user(str(user["id"]), "password_reset")
    issued = auth_email_token_service.issue(
        purpose="password_reset",
        user_id=str(user["id"]),
        email=str(user.get("email") or email),
        tenant_id=tenant_id,
    )
    result = send_reset_password_email(
        to_email=email,
        raw_token=issued,
        otp_code=issued.otp,
        locale=str(user.get("preferredLanguage") or "en"),
        user_id=str(user["id"]),
    )
    payload = dict(generic)
    payload["mail_sent"] = bool(result.sent)
    if not result.sent and "not_configured" in result.reason:
        payload["message"] = (
            "If an account exists for that email, a password reset was prepared. "
            "Mail delivery requires Resend/SMTP configuration on the server."
        )
    return payload


@app.post("/api/auth/reset-password")
async def reset_password(body: ResetPasswordRequest, response: Response) -> Any:
    from services.admin_provisioning_service import validate_provision_password
    from services.auth_email_tokens import auth_email_token_service

    token = (body.token or "").strip()
    if not token:
        return {"success": False, "error": "Reset token is required"}
    try:
        validate_provision_password(body.new_password or "")
    except ValueError as e:
        return {"success": False, "error": str(e)}

    record = auth_email_token_service.consume_link_or_otp(
        token, "password_reset", email=body.email
    )
    if record is None:
        return {"success": False, "error": "Invalid or expired reset link"}

    try:
        await asyncio.wait_for(
            asyncio.to_thread(user_service.set_password_with_reset, record.user_id, body.new_password),
            timeout=AUTH_LOGIN_TIMEOUT_SECONDS,
        )
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        print(f"[auth_api] reset-password error: {e}", flush=True)
        return {"success": False, "error": "Failed to reset password"}

    session_service.revoke_all_for_user(record.user_id)
    _clear_auth_cookies(response)
    try:
        from modules.auth_email_change_api import notify_password_changed

        notify_password_changed(user_id=record.user_id, email=record.email)
    except Exception:
        pass
    return {"success": True, "message": "Password updated. You can sign in with your new password."}


@app.post("/api/auth/verify-email")
async def verify_email(body: VerifyEmailRequest) -> Any:
    from services.auth_email_tokens import auth_email_token_service

    token = (body.token or "").strip()
    if not token:
        return {"success": False, "error": "Verification token is required"}
    record = auth_email_token_service.consume_link_or_otp(token, "email_verify", email=body.email)
    if record is None:
        return {"success": False, "error": "Invalid or expired verification link"}
    try:
        user = await asyncio.wait_for(
            asyncio.to_thread(user_service.mark_email_verified, record.user_id),
            timeout=AUTH_LOGIN_TIMEOUT_SECONDS,
        )
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        print(f"[auth_api] verify-email error: {e}", flush=True)
        return {"success": False, "error": "Failed to verify email"}
    return {"success": True, "message": "Email verified", "user": user}


@app.post("/api/auth/resend-verification")
async def resend_verification(body: ResendVerificationRequest, request: Request) -> Any:
    from services.auth_email_tokens import auth_email_token_service
    from services.email_dispatch import send_verify_email
    from services.mail_service import mail_configured

    email = (body.email or "").strip().lower()
    cookie = request.cookies.get(SESSION_COOKIE_NAME)
    session = session_service.get_valid_session(cookie)

    user = None
    if session is not None:
        user = user_service.get_user_by_id(session.user_id)
    elif email:
        user = user_service.get_user_by_email(email)

    generic = {
        "success": True,
        "message": "If verification is required, a new email has been sent.",
        "mail_configured": mail_configured(),
    }
    if not user or user.get("status") != "active":
        return generic
    if user_service.is_email_verified(user):
        return {"success": True, "message": "Email is already verified", "mail_configured": mail_configured()}

    tenant_id = str(user.get("tenantId") or "").strip()
    if not tenant_id:
        return generic

    auth_email_token_service.revoke_unused_for_user(str(user["id"]), "email_verify")
    issued = auth_email_token_service.issue(
        purpose="email_verify",
        user_id=str(user["id"]),
        email=str(user.get("email") or ""),
        tenant_id=tenant_id,
    )
    result = send_verify_email(
        to_email=str(user.get("email") or ""),
        raw_token=issued,
        otp_code=issued.otp,
        locale=str(user.get("preferredLanguage") or "en"),
        user_id=str(user["id"]),
    )
    payload = dict(generic)
    payload["mail_sent"] = bool(result.sent)
    return payload
