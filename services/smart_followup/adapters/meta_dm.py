"""Instagram / Facebook Messenger Smart Follow-Up adapter."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from db.models.whatsapp_smart_followup import WhatsAppSmartFollowUpJob, WhatsAppSmartFollowUpSettings
from services.requests.constants import SOURCE_CHANNEL_FACEBOOK_MESSENGER, SOURCE_CHANNEL_INSTAGRAM_DM
from services.smart_followup.channels import meta_platform_for_channel, normalize_followup_channel
from services.smart_followup.types import FollowUpConversationView, FollowUpSendResult
from services.smart_followup.window_rules import window_allows_send


def _parse_iso(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    raw = str(value).strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _channel_context(job: WhatsAppSmartFollowUpJob) -> dict[str, Any]:
    ctx = dict(getattr(job, "channel_context", None) or {})
    if not ctx and getattr(job, "sequence", None) is not None:
        ctx = dict(getattr(job.sequence, "channel_context", None) or {})
    return ctx


async def _load_firestore_conversation(*, user_id: str, conversation_id: str) -> dict[str, Any]:
    from utils.utils import get_conversation_history_from_firestore, get_user_state_from_firestore

    state = await get_user_state_from_firestore(user_id) or {}
    history = await get_conversation_history_from_firestore(user_id, conversation_id, max_messages=0, window_hours=48)
    return {"state": state, "history": history or []}


def _latest_customer_inbound_at(history: list[dict[str, Any]]) -> datetime | None:
    latest: datetime | None = None
    for row in history:
        role = str(row.get("role") or "").strip().lower()
        if role not in {"user", "customer"}:
            continue
        ts = _parse_iso(row.get("timestamp") or row.get("created_at"))
        if ts is None:
            continue
        if latest is None or ts > latest:
            latest = ts
    return latest


def _customer_replied_after(history: list[dict[str, Any]], *, after: datetime) -> bool:
    for row in history:
        role = str(row.get("role") or "").strip().lower()
        if role not in {"user", "customer"}:
            continue
        ts = _parse_iso(row.get("timestamp") or row.get("created_at"))
        if ts is None:
            continue
        if ts > after:
            return True
    return False


class MetaDmFollowUpAdapter:
    def __init__(self, *, channel: str) -> None:
        self.channel = normalize_followup_channel(channel)
        if self.channel not in {SOURCE_CHANNEL_INSTAGRAM_DM, SOURCE_CHANNEL_FACEBOOK_MESSENGER}:
            raise ValueError(f"unsupported_meta_followup_channel:{channel}")

    def load_conversation(
        self,
        session: Session,
        *,
        job: WhatsAppSmartFollowUpJob,
    ) -> FollowUpConversationView | None:
        ctx = _channel_context(job)
        user_id = str(ctx.get("user_id") or "").strip()
        if not user_id:
            return None
        last_inbound = _parse_iso(ctx.get("last_inbound_at"))
        return FollowUpConversationView(
            channel=self.channel,
            tenant_id=job.tenant_id,
            conversation_id=job.conversation_id,
            connection_id=job.connection_id,
            control_epoch=int(job.control_epoch),
            control_state="AI_ACTIVE",
            service_window_opens_at=last_inbound,
            last_inbound_at=last_inbound,
            profile_name=str(ctx.get("profile_name") or ""),
            user_id=user_id,
            social_sender_id=str(ctx.get("social_sender_id") or ""),
            asset_id=str(ctx.get("asset_id") or ""),
            meta_binding_id=str(ctx.get("meta_binding_id") or job.connection_id),
            meta_app_key=str(ctx.get("meta_app_key") or ""),
            trigger_ref=str(ctx.get("trigger_ref") or ""),
        )

    async def refresh_conversation(
        self,
        *,
        conv: FollowUpConversationView,
        trigger_ai_sent_at: datetime | None = None,
    ) -> tuple[FollowUpConversationView | None, str | None]:
        if not conv.user_id or not conv.conversation_id:
            return None, "missing_user_or_conversation"
        try:
            payload = await _load_firestore_conversation(user_id=conv.user_id, conversation_id=conv.conversation_id)
        except Exception:
            return None, "firestore_unavailable"

        state = payload.get("state") if isinstance(payload.get("state"), dict) else {}
        history = payload.get("history") if isinstance(payload.get("history"), list) else []
        if bool(state.get("human_takeover_active")):
            return None, "conversation_paused"

        last_inbound = _latest_customer_inbound_at(history) or conv.last_inbound_at
        if trigger_ai_sent_at is not None and _customer_replied_after(history, after=trigger_ai_sent_at):
            return None, "customer_replied"

        refreshed = FollowUpConversationView(
            channel=conv.channel,
            tenant_id=conv.tenant_id,
            conversation_id=conv.conversation_id,
            connection_id=conv.connection_id,
            control_epoch=conv.control_epoch,
            control_state="AI_ACTIVE",
            service_window_opens_at=last_inbound,
            last_inbound_at=last_inbound,
            profile_name=conv.profile_name,
            user_id=conv.user_id,
            social_sender_id=conv.social_sender_id,
            asset_id=conv.asset_id,
            meta_binding_id=conv.meta_binding_id,
            meta_app_key=conv.meta_app_key,
            trigger_ref=conv.trigger_ref,
        )
        return refreshed, None

    def evaluate_channel_eligibility(
        self,
        session: Session,
        *,
        job: WhatsAppSmartFollowUpJob,
        settings: WhatsAppSmartFollowUpSettings | None,
        conv: FollowUpConversationView,
        now: Any | None = None,
    ) -> tuple[bool, str]:
        now_dt = now if isinstance(now, datetime) else datetime.now(UTC)
        platform = meta_platform_for_channel(self.channel)
        from services.channel_capability_state import dm_capability_state

        dm_state = dm_capability_state(job.tenant_id, platform)
        if not dm_state.get("effective_enabled"):
            blocker = str(dm_state.get("blocker_code") or dm_state.get("blocker") or "dm_disabled")
            return False, blocker

        ok_window, window_reason = window_allows_send(conv=conv, now=now_dt)
        if not ok_window:
            return False, window_reason or "window_closed"
        return True, "eligible"

    async def send_followup(
        self,
        session: Session,
        *,
        job: WhatsAppSmartFollowUpJob,
        conv: FollowUpConversationView,
        reply_text: str,
        idempotency_key: str,
    ) -> FollowUpSendResult:
        from services.requests.delivery import deliver_meta_dm

        ctx = _channel_context(job)
        recipient = str(conv.social_sender_id or ctx.get("social_sender_id") or "").strip()
        account = str(conv.asset_id or ctx.get("asset_id") or "").strip()
        if not recipient or not account:
            return FollowUpSendResult(status="failed", reason="missing_recipient_or_account")

        result = await deliver_meta_dm(
            tenant_id=job.tenant_id,
            source_channel=self.channel,
            source_account_id=account,
            external_customer_id=recipient,
            text=reply_text,
        )
        if result.status == "sent":
            return FollowUpSendResult(
                status="sent",
                reason="sent",
                provider_message_id=result.provider_message_id,
            )
        if result.status == "blocked":
            return FollowUpSendResult(status="skipped", reason="platform_blocked", detail=result.error_redacted)
        return FollowUpSendResult(status="failed", reason="send_failed", detail=result.error_redacted)
