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
    WHATSAPP_REQUIRED_SCOPES,
    get_whatsapp_cloud_flags,
)
from services.whatsapp_cloud.embedded_signup_session import (
    SignupAssetError,
    resolve_signup_phone,
    session_event_is_cancel,
)
from services.whatsapp_cloud.entitlement import WhatsAppEntitlementError, assert_whatsapp_connection_allowed
from services.whatsapp_cloud.graph_client import (
    WhatsAppGraphError,
    debug_token,
    exchange_embedded_signup_code,
    fetch_waba_phone_numbers,
    initiate_smb_app_data_sync,
    subscribe_waba_webhooks,
)
from services.whatsapp_cloud.observability import emit_wa_event
from services.whatsapp_cloud.repository import WhatsAppCloudRepository, connection_public_view


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
            # Never return secrets/tokens.
        }


async def complete_embedded_signup(
    *,
    state: str,
    code: str | None,
    waba_id: str | None,
    phone_number_id: str | None,
    error: str | None = None,
    error_reason: str | None = None,
    session_event: str | None = None,
) -> dict[str, Any]:
    """Exchange code, verify assets, persist connection, subscribe WABA. No credentials to client."""

    nonce = str(state or "").strip()
    if not nonce:
        raise WhatsAppSignupError("missing_state", "state is required")
    if session_event_is_cancel(session_event or ""):
        error = error or "user_cancelled"
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

        if error or not code:
            try:
                repo.consume_attempt(
                    attempt,
                    outcome_code=str(error or "cancelled"),
                    outcome_detail=(error_reason or "")[:255] or None,
                    status="cancelled"
                    if (error or "").lower() in {"access_denied", "user_cancelled", "cancelled"}
                    else "failed",
                )
            except ValueError as exc:
                raise WhatsAppSignupError(str(exc), "state not consumable") from exc
            emit_wa_event(
                "connection_failure",
                tenant_id=tenant_id,
                correlation_id=correlation_id,
                reason=str(error or "cancelled"),
            )
            redirect = oauth_completion_redirect_url(
                return_surface="mobile" if return_surface == "mobile" else "web",
                meta_connection="cancelled"
                if (error or "").lower() in {"access_denied", "user_cancelled", "cancelled"}
                else "failed",
                extra_query={"wa_connection": "cancelled" if error else "failed", "correlation_id": correlation_id},
            )
            # Mobile deep-link uses meta_connection; also include wa_connection for WA card.
            if return_surface == "mobile":
                from urllib.parse import urlencode as _ue

                status = (
                    "cancelled"
                    if (error or "").lower() in {"access_denied", "user_cancelled", "cancelled"}
                    else "failed"
                )
                redirect = f"linasai://integrations?{_ue({'wa_connection': status, 'correlation_id': correlation_id})}"
            return {"success": False, "redirect_url": redirect, "correlation_id": correlation_id}

        try:
            repo.consume_attempt(attempt, outcome_code="code_received", status="consumed")
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
            scopes_raw = dbg.get("scopes") if isinstance(dbg, dict) else None
            scopes = [str(s) for s in scopes_raw] if isinstance(scopes_raw, list) else []
            granted = set(scopes)
            if not WHATSAPP_REQUIRED_SCOPES.issubset(granted):
                raise WhatsAppSignupError(
                    "scopes_missing",
                    "Embedded Signup did not grant required WhatsApp permissions",
                    http_status=403,
                )
            # Asset IDs come from sessionInfo. Coexistence FINISH often omits phone_number_id.
            waba = str(waba_id or "").strip()
            try:
                from services.whatsapp_cloud.embedded_signup_session import assert_not_placeholder_id

                assert_not_placeholder_id(waba, field="waba_id")
            except SignupAssetError as exc:
                raise WhatsAppSignupError(exc.code, exc.message) from exc
            phones = await fetch_waba_phone_numbers(access_token=access_token, waba_id=waba)
            try:
                matched = resolve_signup_phone(
                    waba_id=waba,
                    phone_number_id=phone_number_id,
                    phones=phones,
                )
            except SignupAssetError as exc:
                status = 403 if exc.code == "phone_not_in_waba" else 400
                raise WhatsAppSignupError(exc.code, exc.message, http_status=status) from exc
            phone = str(matched.get("id") or "").strip()
            # Fail closed: never allow ordinary API Setup path — coexistence feature only.
            if attempt.feature_type != WHATSAPP_COEXISTENCE_FEATURE:
                raise WhatsAppSignupError("coexistence_required", "only coexistence onboarding is permitted")

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
                scopes=sorted(granted & (WHATSAPP_REQUIRED_SCOPES | {"business_management"})),
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
            # Same as Facebook/Instagram: Connect turns Messages ON. The switch only controls AI.
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
            repo.add_audit(
                tenant_id=tenant_id,
                connection_id=conn.id,
                actor_user_id=actor,
                event_type="connection_completed",
                detail={
                    "correlation_id": correlation_id,
                    "session_event": (session_event or "")[:80],
                    "waba_masked": waba[:3] + "…" + waba[-3:],
                    "phone_masked": phone[:3] + "…" + phone[-3:],
                    "subscribe_ok": bool(sub.get("success", True)),
                    "is_on_biz_app": matched.get("is_on_biz_app"),
                    "platform_type": matched.get("platform_type"),
                    "history_sync_started": sync_started,
                },
            )
            emit_wa_event("connection_completed", tenant_id=tenant_id, connection_id=conn.id)
            view = connection_public_view(conn, ai_eligible=True, rollout_blocked_reason=None)
            if return_surface == "mobile":
                from urllib.parse import urlencode as _ue

                redirect = (
                    f"linasai://integrations?{_ue({'wa_connection': 'success', 'correlation_id': correlation_id})}"
                )
            else:
                redirect = oauth_completion_redirect_url(
                    return_surface="web",
                    meta_connection="success",
                    extra_query={"wa_connection": "success", "correlation_id": correlation_id},
                )
            return {
                "success": True,
                "redirect_url": redirect,
                "correlation_id": correlation_id,
                "connection": view,
            }
        except (WhatsAppGraphError, WhatsAppEntitlementError, WhatsAppSignupError, PermissionError) as exc:
            code_name = getattr(exc, "code", type(exc).__name__)
            repo.add_audit(
                tenant_id=tenant_id,
                actor_user_id=actor,
                event_type="connection_failure",
                detail={"correlation_id": correlation_id, "error_code": str(code_name)},
            )
            emit_wa_event(
                "connection_failure",
                tenant_id=tenant_id,
                correlation_id=correlation_id,
                reason=str(code_name),
            )
            if return_surface == "mobile":
                from urllib.parse import urlencode as _ue

                redirect = (
                    f"linasai://integrations?{_ue({'wa_connection': 'failed', 'correlation_id': correlation_id})}"
                )
            else:
                redirect = oauth_completion_redirect_url(
                    return_surface="web",
                    meta_connection="failed",
                    extra_query={"wa_connection": "failed", "correlation_id": correlation_id},
                )
            if isinstance(exc, WhatsAppSignupError):
                raise
            raise WhatsAppSignupError(str(code_name), "WhatsApp connection failed", http_status=400) from exc
