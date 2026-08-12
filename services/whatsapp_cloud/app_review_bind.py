"""Temporary Meta App Review WhatsApp bind for tenant linas.

Creates a real PostgreSQL whatsapp_connections row (no fake UI). Credentials are
sealed with the existing AES-GCM path. Public availability is never flipped.

Helpers: app_review_bind_helpers (LOC split).
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Any

from db.session import whatsapp_session
from services.meta_app_registry import APP_A_KEY, get_meta_app_configs
from services.whatsapp_cloud.app_review_bind_helpers import (
    APP_REVIEW_SOURCE,
    APP_REVIEW_TENANT_ID,
    AppReviewBindError,
    _assert_numeric_ids,
    _assert_tenant,
    _correlation_id,
    _is_app_review_connection,
    _mask_id,
    _require_token,
    _validate_meta_assets,
)
from services.whatsapp_cloud.config import get_whatsapp_cloud_flags
from services.whatsapp_cloud.graph_client import WhatsAppGraphError, subscribe_waba_webhooks
from services.whatsapp_cloud.observability import emit_wa_event
from services.whatsapp_cloud.repository import (
    ACTIVE_LIFECYCLES,
    WhatsAppCloudRepository,
    connection_public_view,
)

APP_REVIEW_REASON = "meta_app_review_test"

WEBHOOK_FIELDS = [
    "messages",
    "message_template_status_update",
    "smb_message_echoes",
    "history",
    "smb_app_state_sync",
    "account_update",
    "phone_number_quality_update",
]

@dataclass
class AppReviewBindResult:
    success: bool
    action: str
    correlation_id: str
    connection_id: str | None
    tenant_id: str
    lifecycle_status: str | None
    display_phone_last4: str | None
    waba_id_masked: str | None
    phone_number_id_masked: str | None
    dry_run: bool
    detail: dict[str, Any]

    def public_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "action": self.action,
            "correlation_id": self.correlation_id,
            "connection_id": self.connection_id,
            "tenant_id": self.tenant_id,
            "lifecycle_status": self.lifecycle_status,
            "display_phone_last4": self.display_phone_last4,
            "waba_id_masked": self.waba_id_masked,
            "phone_number_id_masked": self.phone_number_id_masked,
            "dry_run": self.dry_run,
            "detail": self.detail,
            "connection_source": APP_REVIEW_SOURCE,
            "public_availability": get_whatsapp_cloud_flags().public_availability,
        }


def status_app_review_bind(*, tenant_id: str = APP_REVIEW_TENANT_ID) -> dict[str, Any]:
    tid = _assert_tenant(tenant_id)
    flags = get_whatsapp_cloud_flags()
    with whatsapp_session() as session:
        repo = WhatsAppCloudRepository(session)
        history = [
            c for c in repo.list_tenant_connections(tenant_id=tid, include_revoked=True) if _is_app_review_connection(c)
        ]
        active = [
            c
            for c in repo.list_tenant_connections(tenant_id=tid, include_revoked=False)
            if _is_app_review_connection(c) and c.lifecycle_status in ACTIVE_LIFECYCLES
        ]
        primary = active[0] if active else None
        return {
            "success": True,
            "tenant_id": tid,
            "public_availability": flags.public_availability,
            "connection_source": APP_REVIEW_SOURCE,
            "active_count": len(active),
            "connection": connection_public_view(primary, ai_eligible=bool(primary and primary.ai_default_enabled))
            if primary
            else None,
            "active_connections": [connection_public_view(c, ai_eligible=bool(c.ai_default_enabled)) for c in active],
            "history_count": len(history),
        }


async def dry_run_app_review_bind(
    *,
    tenant_id: str,
    waba_id: str,
    phone_number_id: str,
    access_token: str | None,
    actor_user_id: str,
    idempotency_key: str | None = None,
) -> AppReviewBindResult:
    tid = _assert_tenant(tenant_id)
    waba, phone = _assert_numeric_ids(waba_id=waba_id, phone_number_id=phone_number_id)
    token = _require_token(access_token)
    correlation_id = _correlation_id(idempotency_key)
    matched, scopes, dbg = await _validate_meta_assets(access_token=token, waba_id=waba, phone_number_id=phone)
    display = str(matched.get("display_phone_number") or "")
    last4 = "".join(ch for ch in display if ch.isdigit())[-4:]
    with whatsapp_session() as session:
        repo = WhatsAppCloudRepository(session)
        existing = repo.find_active_by_phone_number_id(phone)
        collision = None
        if existing is not None:
            collision = {
                "tenant_id": existing.tenant_id,
                "connection_id": existing.id,
                "lifecycle_status": existing.lifecycle_status,
                "same_tenant": existing.tenant_id == tid,
                "is_app_review": _is_app_review_connection(existing),
            }
        would_succeed = collision is None or (
            bool(collision.get("same_tenant")) and bool(collision.get("is_app_review"))
        )
    flags = get_whatsapp_cloud_flags()
    return AppReviewBindResult(
        success=would_succeed,
        action="dry_run",
        correlation_id=correlation_id,
        connection_id=None,
        tenant_id=tid,
        lifecycle_status=None,
        display_phone_last4=last4 or None,
        waba_id_masked=_mask_id(waba),
        phone_number_id_masked=_mask_id(phone),
        dry_run=True,
        detail={
            "actor_user_id": actor_user_id,
            "reason": APP_REVIEW_REASON,
            "verified_name_present": bool(matched.get("verified_name")),
            "scopes_count": len(scopes),
            "token_app_id": str(dbg.get("app_id") or ""),
            "collision": collision,
            "public_availability": flags.public_availability,
            "would_enable_ai_default": True,
            "would_grant_pilot_if_missing": True,
            "subscribe_webhooks": True,
        },
    )


async def bind_app_review_test_number(
    *,
    tenant_id: str,
    waba_id: str,
    phone_number_id: str,
    access_token: str | None,
    actor_user_id: str,
    idempotency_key: str | None = None,
    dry_run: bool = False,
) -> AppReviewBindResult:
    if dry_run:
        return await dry_run_app_review_bind(
            tenant_id=tenant_id,
            waba_id=waba_id,
            phone_number_id=phone_number_id,
            access_token=access_token,
            actor_user_id=actor_user_id,
            idempotency_key=idempotency_key,
        )

    tid = _assert_tenant(tenant_id)
    waba, phone = _assert_numeric_ids(waba_id=waba_id, phone_number_id=phone_number_id)
    token = _require_token(access_token)
    correlation_id = _correlation_id(idempotency_key or f"bind:{tid}:{phone}")
    matched, scopes, _dbg = await _validate_meta_assets(access_token=token, waba_id=waba, phone_number_id=phone)
    display = str(matched.get("display_phone_number") or "")
    verified_name = str(matched.get("verified_name") or "")
    app = get_meta_app_configs()[APP_A_KEY]

    with whatsapp_session() as session:
        repo = WhatsAppCloudRepository(session)
        existing = repo.find_active_by_phone_number_id(phone)
        if existing is not None and existing.tenant_id != tid:
            raise AppReviewBindError("phone_owned_elsewhere", "phone_number_id is already bound to another tenant")
        if existing is not None and existing.tenant_id == tid:
            if _is_app_review_connection(existing) and existing.lifecycle_status == "connected":
                view = connection_public_view(existing, ai_eligible=bool(existing.ai_default_enabled))
                repo.add_audit(
                    tenant_id=tid,
                    connection_id=existing.id,
                    actor_user_id=actor_user_id,
                    event_type="app_review_bind_idempotent",
                    detail={"correlation_id": correlation_id, "source": APP_REVIEW_SOURCE},
                )
                return AppReviewBindResult(
                    success=True,
                    action="bind_idempotent",
                    correlation_id=correlation_id,
                    connection_id=existing.id,
                    tenant_id=tid,
                    lifecycle_status=existing.lifecycle_status,
                    display_phone_last4=existing.display_phone_last4,
                    waba_id_masked=_mask_id(existing.waba_id),
                    phone_number_id_masked=_mask_id(existing.phone_number_id),
                    dry_run=False,
                    detail={"replay": True, "connection": view},
                )
            if not _is_app_review_connection(existing):
                raise AppReviewBindError(
                    "phone_already_bound",
                    "phone_number_id already has a non app-review connection for linas; refusing overwrite",
                )
            # Incomplete prior app-review attempt — clean up before rebinding.
            repo.revoke_connection(existing, actor_user_id=actor_user_id, reason="app_review_rebind_cleanup")

        # Pilot required while public_availability stays false.
        if repo.get_active_pilot(tid) is None:
            repo.grant_pilot(
                tenant_id=tid,
                granted_by_user_id=actor_user_id,
                reason=APP_REVIEW_REASON,
            )
            repo.add_audit(
                tenant_id=tid,
                actor_user_id=actor_user_id,
                event_type="pilot_granted",
                detail={"reason": APP_REVIEW_REASON, "source": APP_REVIEW_SOURCE},
            )

        try:
            conn = repo.create_connection_with_credential(
                tenant_id=tid,
                created_by_user_id=actor_user_id,
                meta_app_key=APP_A_KEY,
                meta_app_id=app.app_id,
                waba_id=waba,
                phone_number_id=phone,
                display_phone_number=display,
                verified_name=verified_name,
                access_token=token,
                scopes=scopes,
                connection_source=APP_REVIEW_SOURCE,
            )
        except PermissionError as exc:
            raise AppReviewBindError("phone_owned_elsewhere", str(exc)) from exc

        try:
            sub = await subscribe_waba_webhooks(access_token=token, waba_id=waba)
        except WhatsAppGraphError as exc:
            repo.revoke_connection(conn, actor_user_id=actor_user_id, reason="subscribe_failed_rollback")
            raise AppReviewBindError("waba_subscribe_failed", exc.message) from exc

        repo.mark_connection_connected(conn, webhook_fields=WEBHOOK_FIELDS)
        # App Review video needs AI replies; keep public availability false.
        conn.ai_default_enabled = True
        conn.history_sync_status = "skipped"
        conn.health_detail = APP_REVIEW_SOURCE
        repo.add_audit(
            tenant_id=tid,
            connection_id=conn.id,
            actor_user_id=actor_user_id,
            event_type="app_review_bind",
            detail={
                "correlation_id": correlation_id,
                "source": APP_REVIEW_SOURCE,
                "reason": APP_REVIEW_REASON,
                "waba_masked": _mask_id(waba),
                "phone_masked": _mask_id(phone),
                "display_last4": conn.display_phone_last4,
                "subscribe_ok": bool(sub.get("success", True)),
                "ai_default_enabled": True,
            },
        )
        emit_wa_event("app_review_bind", tenant_id=tid, connection_id=conn.id)
        view = connection_public_view(conn, ai_eligible=True)
        return AppReviewBindResult(
            success=True,
            action="bind",
            correlation_id=correlation_id,
            connection_id=conn.id,
            tenant_id=tid,
            lifecycle_status=conn.lifecycle_status,
            display_phone_last4=conn.display_phone_last4,
            waba_id_masked=_mask_id(conn.waba_id),
            phone_number_id_masked=_mask_id(conn.phone_number_id),
            dry_run=False,
            detail={"connection": view},
        )


def unbind_app_review_test_number(
    *,
    tenant_id: str = APP_REVIEW_TENANT_ID,
    actor_user_id: str,
    connection_id: str | None = None,
    idempotency_key: str | None = None,
) -> AppReviewBindResult:
    tid = _assert_tenant(tenant_id)
    correlation_id = _correlation_id(idempotency_key or f"unbind:{tid}:{secrets.token_hex(8)}")
    with whatsapp_session() as session:
        repo = WhatsAppCloudRepository(session)
        target = None
        if connection_id:
            target = repo.get_tenant_connection(tenant_id=tid, connection_id=connection_id)
            if target is None:
                raise AppReviewBindError("connection_not_found", "connection not found for tenant linas")
            if not _is_app_review_connection(target):
                raise AppReviewBindError("not_app_review_bind", "refusing to unbind a non app-review connection")
            if target.lifecycle_status == "revoked":
                return AppReviewBindResult(
                    success=True,
                    action="unbind_idempotent",
                    correlation_id=correlation_id,
                    connection_id=target.id,
                    tenant_id=tid,
                    lifecycle_status=target.lifecycle_status,
                    display_phone_last4=target.display_phone_last4,
                    waba_id_masked=_mask_id(target.waba_id),
                    phone_number_id_masked=_mask_id(target.phone_number_id),
                    dry_run=False,
                    detail={"replay": True, "message": "already revoked"},
                )
        else:
            candidates = [
                c
                for c in repo.list_tenant_connections(tenant_id=tid, include_revoked=False)
                if _is_app_review_connection(c)
            ]
            if not candidates:
                return AppReviewBindResult(
                    success=True,
                    action="unbind_noop",
                    correlation_id=correlation_id,
                    connection_id=None,
                    tenant_id=tid,
                    lifecycle_status=None,
                    display_phone_last4=None,
                    waba_id_masked=None,
                    phone_number_id_masked=None,
                    dry_run=False,
                    detail={"message": "no active app-review connection"},
                )
            if len(candidates) > 1:
                raise AppReviewBindError(
                    "ambiguous_connection",
                    "multiple app-review connections found; pass connection_id",
                )
            target = candidates[0]

        assert target is not None
        phone = target.phone_number_id
        suppressed = repo.suppress_pending_outbound_for_connection(
            connection_id=target.id,
            tenant_id=tid,
            reason="app_review_unbind",
        )
        from services.whatsapp_cloud.smart_followup.hooks import cancel_connection_followups

        followups = cancel_connection_followups(
            session,
            tenant_id=tid,
            connection_id=target.id,
            reason="app_review_unbind",
        )

        repo.revoke_connection(target, actor_user_id=actor_user_id, reason=APP_REVIEW_REASON)
        repo.add_audit(
            tenant_id=tid,
            connection_id=target.id,
            actor_user_id=actor_user_id,
            event_type="app_review_unbind",
            detail={
                "correlation_id": correlation_id,
                "source": APP_REVIEW_SOURCE,
                "reason": APP_REVIEW_REASON,
                "phone_masked": _mask_id(phone),
                "outbound_suppressed": suppressed,
                "followups_cancelled": followups,
            },
        )
        emit_wa_event("app_review_unbind", tenant_id=tid, connection_id=target.id)
        still = repo.find_active_by_phone_number_id(phone)
        return AppReviewBindResult(
            success=True,
            action="unbind",
            correlation_id=correlation_id,
            connection_id=target.id,
            tenant_id=tid,
            lifecycle_status=target.lifecycle_status,
            display_phone_last4=target.display_phone_last4,
            waba_id_masked=_mask_id(target.waba_id),
            phone_number_id_masked=_mask_id(phone),
            dry_run=False,
            detail={
                "phone_still_active": still is not None,
                "outbound_suppressed": suppressed,
                "followups_cancelled": followups,
                "public_availability": get_whatsapp_cloud_flags().public_availability,
            },
        )
