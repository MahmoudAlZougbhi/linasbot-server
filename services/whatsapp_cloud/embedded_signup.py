"""Embedded Signup v4 start/complete for WhatsApp Business App Coexistence only."""

from __future__ import annotations

import hashlib
import os
from typing import Any
from urllib.parse import urlencode

from db.session import whatsapp_session
from services.meta_app_registry import APP_A_EXPECTED_ID, APP_A_KEY, get_meta_app_configs
from services.meta_oauth_return import oauth_completion_redirect_url
from services.whatsapp_cloud.config import (
    WHATSAPP_COEXISTENCE_FEATURE,
    WHATSAPP_OPTIONAL_SCOPES,
    WHATSAPP_REQUIRED_SCOPES,
    get_whatsapp_cloud_flags,
)
from services.whatsapp_cloud.embedded_signup_proof import prove_coexistence_phone
from services.whatsapp_cloud.embedded_signup_session import (
    SignupAssetError,
    assert_coexistence_session,
    assert_not_placeholder_id,
    session_event_is_cancel,
)
from services.whatsapp_cloud.embedded_signup_token import validate_embedded_signup_token
from services.whatsapp_cloud.entitlement import WhatsAppEntitlementError, assert_whatsapp_connection_allowed
from services.whatsapp_cloud.graph_client import (
    WhatsAppGraphError,
    debug_token,
    exchange_embedded_signup_code,
    initiate_smb_app_data_sync,
    subscribe_waba_webhooks,
)
from services.whatsapp_cloud.observability import emit_wa_event
from services.whatsapp_cloud.repository import WhatsAppCloudRepository, connection_public_view

_CANCEL_ERRORS = frozenset({"access_denied", "user_cancelled", "cancelled", "canceled"})
_FRIENDLY_FAIL_ERRORS = frozenset(
    {
        "coexistence_flow_required",
        "meta_advanced_access_required",
        "advanced_access_required",
        "session_timeout",
        "embedded_signup_timeout",
        "embedded_signup_error",
        "meta_embedded_signup_error",
        "session_version_invalid",
        "login_failed",
        "missing_code",
        "session_error",
    }
)


class WhatsAppSignupError(RuntimeError):
    def __init__(self, code: str, message: str, *, http_status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


def _app_a_secrets() -> tuple[str, str]:
    configs = get_meta_app_configs()
    app = configs.get(APP_A_KEY)
    if app is None or not app.enabled or app.app_id != APP_A_EXPECTED_ID:
        raise WhatsAppSignupError("app_a_unavailable", "Meta App A is not configured", http_status=503)
    return app.app_id, app.app_secret


def _wa_redirect(
    return_surface: str,
    *,
    status: str,
    correlation_id: str,
    error_code: str | None = None,
) -> str:
    extra: dict[str, str] = {"wa_connection": status, "correlation_id": correlation_id}
    if error_code:
        extra["wa_error"] = error_code
    if return_surface == "mobile":
        return f"linasai://integrations?{urlencode(extra)}"
    meta_status = "success" if status == "success" else ("cancelled" if status == "cancelled" else "failed")
    return oauth_completion_redirect_url(
        return_surface="web",
        meta_connection=meta_status,
        extra_query=extra,
    )


def start_embedded_signup(
    *,
    tenant_id: str,
    actor_user_id: str,
    return_surface: str,
) -> dict[str, Any]:
    flags = get_whatsapp_cloud_flags()
    config_id = (os.getenv("META_WHATSAPP_EMBEDDED_SIGNUP_CONFIG_ID") or "").strip()
    if not config_id:
        raise WhatsAppSignupError(
            "embedded_signup_config_missing",
            "WhatsApp Embedded Signup is not configured on the server",
            http_status=503,
        )
    bridge_url = (flags.bridge_base_url or "").strip()
    if not bridge_url.lower().startswith("https://"):
        raise WhatsAppSignupError(
            "bridge_url_misconfigured",
            "WhatsApp Embedded Signup bridge URL is missing or not HTTPS",
            http_status=503,
        )
    if not flags.meta_app_id:
        raise WhatsAppSignupError(
            "meta_app_unavailable",
            "Meta App A is not configured for WhatsApp Embedded Signup",
            http_status=503,
        )
    with whatsapp_session() as session:
        assert_whatsapp_connection_allowed(session, tenant_id)
        if return_surface not in {"mobile", "web", "bridge"}:
            raise WhatsAppSignupError("invalid_return_surface", "return_surface must be mobile|web|bridge")
        repo = WhatsAppCloudRepository(session)
        attempt, nonce = repo.create_connection_attempt(
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            return_surface=return_surface,
            meta_app_key=APP_A_KEY,
        )
        repo.add_audit(
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            event_type="connection_start",
            detail={"correlation_id": attempt.correlation_id, "return_surface": return_surface},
        )
        query = urlencode(
            {
                "state": nonce,
                "correlation_id": attempt.correlation_id,
                "config_id": config_id,
                "feature_type": WHATSAPP_COEXISTENCE_FEATURE,
                "app_id": flags.meta_app_id,
            }
        )
        authorization_url = f"{bridge_url}?{query}"
        emit_wa_event("connection_start", tenant_id=tenant_id, correlation_id=attempt.correlation_id)
        return {
            "success": True,
            "authorization_url": authorization_url,
            "correlation_id": attempt.correlation_id,
            "feature_type": WHATSAPP_COEXISTENCE_FEATURE,
            "expires_at": attempt.expires_at.isoformat(),
        }


def _fail_attempt(
    repo: WhatsAppCloudRepository,
    attempt: Any,
    *,
    code: str,
    detail: str | None,
    status: str,
) -> None:
    try:
        repo.consume_attempt(attempt, outcome_code=code, outcome_detail=(detail or "")[:255] or None, status=status)
    except ValueError as exc:
        raise WhatsAppSignupError(str(exc), "state not consumable") from exc


async def complete_embedded_signup(
    *,
    state: str,
    code: str | None,
    waba_id: str | None,
    phone_number_id: str | None,
    error: str | None = None,
    error_reason: str | None = None,
    session_event: str | None = None,
    session_type: str | None = None,
    session_version: str | None = None,
    business_id: str | None = None,
) -> dict[str, Any]:
    """Exchange code only after coexistence finish + Graph proof. Never register."""

    nonce = str(state or "").strip()
    if not nonce:
        raise WhatsAppSignupError("missing_state", "state is required")
    reported_event = str(session_event or "").strip()
    if session_event_is_cancel(reported_event):
        error = error or "user_cancelled"
    inbound_error = str(error or "").strip()
    state_hash = hashlib.sha256(nonce.encode("utf-8")).hexdigest()

    with whatsapp_session() as session:
        repo = WhatsAppCloudRepository(session)
        attempt = repo.get_attempt_by_state_hash(state_hash)
        if attempt is None:
            raise WhatsAppSignupError("invalid_state", "unknown or already consumed state", http_status=400)
        return_surface = attempt.return_surface
        tenant_id = attempt.tenant_id
        actor = attempt.actor_user_id
        correlation_id = attempt.correlation_id
        event_detail = reported_event or inbound_error or None

        if inbound_error in _FRIENDLY_FAIL_ERRORS or inbound_error.lower() in _CANCEL_ERRORS or not code:
            status = "cancelled" if inbound_error.lower() in _CANCEL_ERRORS else "failed"
            outcome = inbound_error or "cancelled"
            _fail_attempt(repo, attempt, code=outcome, detail=event_detail, status=status)
            emit_wa_event("connection_failure", tenant_id=tenant_id, correlation_id=correlation_id, reason=outcome)
            redirect_status = "cancelled" if status == "cancelled" else "failed"
            return {
                "success": False,
                "redirect_url": _wa_redirect(
                    return_surface,
                    status=redirect_status,
                    correlation_id=correlation_id,
                    error_code=outcome if outcome in _FRIENDLY_FAIL_ERRORS else None,
                ),
                "correlation_id": correlation_id,
                "error": outcome,
            }

        try:
            assert_coexistence_session(
                session_type=session_type,
                session_event=reported_event,
                session_version=session_version,
            )
        except SignupAssetError as exc:
            _fail_attempt(repo, attempt, code=exc.code, detail=reported_event, status="failed")
            emit_wa_event("connection_failure", tenant_id=tenant_id, correlation_id=correlation_id, reason=exc.code)
            return {
                "success": False,
                "redirect_url": _wa_redirect(
                    return_surface,
                    status="failed",
                    correlation_id=correlation_id,
                    error_code=exc.code,
                ),
                "correlation_id": correlation_id,
                "error": exc.code,
            }

        try:
            repo.consume_attempt(
                attempt,
                outcome_code="code_received",
                outcome_detail=f"event={reported_event}"[:255],
                status="consumed",
            )
        except ValueError as exc:
            raise WhatsAppSignupError(str(exc), "state not consumable") from exc

        flags = get_whatsapp_cloud_flags()
        app_id, app_secret = _app_a_secrets()
        redirect_uri = flags.oauth_redirect_uri
        try:
            token_payload = await exchange_embedded_signup_code(
                code=code,
                redirect_uri=redirect_uri,
                app_id=app_id,
                app_secret=app_secret,
            )
            access_token = str(token_payload.get("access_token") or "").strip()
            if not access_token:
                raise WhatsAppGraphError("missing_token", "token exchange returned no access_token")
            dbg = await debug_token(input_token=access_token, app_id=app_id, app_secret=app_secret)
            waba = assert_not_placeholder_id(str(waba_id or "").strip(), field="waba_id")
            granted = validate_embedded_signup_token(dbg, waba_id=waba)
            matched = await prove_coexistence_phone(
                access_token=access_token,
                waba_id=waba,
                phone_number_id=str(phone_number_id or "").strip() or None,
            )
            phone = str(matched.get("id") or "").strip()
            display = str(matched.get("display_phone_number") or "")
            verified_name = str(matched.get("verified_name") or "")
            conn = repo.create_connection_with_credential(
                tenant_id=tenant_id,
                created_by_user_id=actor,
                meta_app_key=APP_A_KEY,
                meta_app_id=app_id,
                waba_id=waba,
                phone_number_id=phone,
                display_phone_number=display,
                verified_name=verified_name,
                access_token=access_token,
                scopes=sorted(set(granted) & (WHATSAPP_REQUIRED_SCOPES | WHATSAPP_OPTIONAL_SCOPES)),
            )
            sub = await subscribe_waba_webhooks(access_token=access_token, waba_id=waba)
            fields = [
                "messages",
                "message_template_status_update",
                "smb_message_echoes",
                "history",
                "smb_app_state_sync",
                "account_update",
                "phone_number_quality_update",
            ]
            repo.mark_connection_connected(conn, webhook_fields=fields)
            conn.ai_default_enabled = True
            sync_started = False
            try:
                await initiate_smb_app_data_sync(
                    access_token=access_token,
                    phone_number_id=phone,
                    sync_type="smb_app_state_sync",
                )
                await initiate_smb_app_data_sync(
                    access_token=access_token,
                    phone_number_id=phone,
                    sync_type="history",
                )
                sync_started = True
            except WhatsAppGraphError as sync_exc:
                emit_wa_event(
                    "history_sync_start_failed",
                    tenant_id=tenant_id,
                    correlation_id=correlation_id,
                    reason=str(sync_exc.code),
                )
            conn.history_sync_status = "pending" if sync_started else "skipped"
            attempt.status = "completed"
            attempt.outcome_code = "connected"
            attempt.outcome_detail = f"event={reported_event}"[:255]
            repo.add_audit(
                tenant_id=tenant_id,
                connection_id=conn.id,
                actor_user_id=actor,
                event_type="connection_completed",
                detail={
                    "correlation_id": correlation_id,
                    "session_event": reported_event[:80],
                    "session_version": str(session_version or "")[:16],
                    "waba_masked": "***" + waba[-3:] if len(waba) >= 3 else "***",
                    "phone_masked": "***" + phone[-3:] if len(phone) >= 3 else "***",
                    "subscribe_ok": bool(sub.get("success", True)),
                    "is_on_biz_app": matched.get("is_on_biz_app"),
                    "platform_type": matched.get("platform_type"),
                    "quality_rating": str(matched.get("quality_rating") or ""),
                    "history_sync_started": sync_started,
                    "coexistence_mode": conn.coexistence_mode,
                    "business_id_present": bool(str(business_id or "").strip()),
                },
            )
            emit_wa_event("connection_completed", tenant_id=tenant_id, connection_id=conn.id)
            view = connection_public_view(conn, ai_eligible=True, rollout_blocked_reason=None)
            return {
                "success": True,
                "redirect_url": _wa_redirect(return_surface, status="success", correlation_id=correlation_id),
                "correlation_id": correlation_id,
                "connection": view,
            }
        except (SignupAssetError, WhatsAppGraphError, WhatsAppEntitlementError, WhatsAppSignupError, PermissionError) as exc:
            code_name = str(getattr(exc, "code", type(exc).__name__))[:80]
            attempt.status = "failed"
            attempt.outcome_code = code_name
            attempt.outcome_detail = reported_event[:255] or None
            repo.add_audit(
                tenant_id=tenant_id,
                actor_user_id=actor,
                event_type="connection_failure",
                detail={"correlation_id": correlation_id, "error_code": code_name},
            )
            emit_wa_event(
                "connection_failure",
                tenant_id=tenant_id,
                correlation_id=correlation_id,
                reason=code_name,
            )
            return {
                "success": False,
                "redirect_url": _wa_redirect(
                    return_surface,
                    status="failed",
                    correlation_id=correlation_id,
                    error_code=code_name,
                ),
                "correlation_id": correlation_id,
                "error": code_name,
            }
