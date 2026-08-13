"""Channel adapter protocol for Smart Follow-Up."""

from __future__ import annotations

from typing import Any, Protocol

from sqlalchemy.orm import Session

from db.models.whatsapp_smart_followup import WhatsAppSmartFollowUpJob, WhatsAppSmartFollowUpSettings
from services.smart_followup.types import FollowUpConversationView, FollowUpSendResult


class SmartFollowUpChannelAdapter(Protocol):
    channel: str

    def load_conversation(
        self,
        session: Session,
        *,
        job: WhatsAppSmartFollowUpJob,
    ) -> FollowUpConversationView | None: ...

    def evaluate_channel_eligibility(
        self,
        session: Session,
        *,
        job: WhatsAppSmartFollowUpJob,
        settings: WhatsAppSmartFollowUpSettings | None,
        conv: FollowUpConversationView,
        now: Any | None = None,
    ) -> tuple[bool, str]: ...

    async def send_followup(
        self,
        session: Session,
        *,
        job: WhatsAppSmartFollowUpJob,
        conv: FollowUpConversationView,
        reply_text: str,
        idempotency_key: str,
    ) -> FollowUpSendResult: ...
