"""
Models module: Pydantic models for WhatsApp messages and requests
Defines all request/response models for API endpoints and webhook processing.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# Base model to allow extra fields without error
class FlexibleBaseModel(BaseModel):
    class Config:
        extra = "ignore"


# WhatsApp Message Content Types
class WhatsAppText(FlexibleBaseModel):
    body: str


class WhatsAppImage(FlexibleBaseModel):
    id: str
    mime_type: str
    sha256: str | None = None


class WhatsAppAudio(FlexibleBaseModel):
    id: str
    mime_type: str
    voice: bool | None = None


class WhatsAppVideo(FlexibleBaseModel):
    id: str
    mime_type: str
    sha256: str | None = None


class WhatsAppDocument(FlexibleBaseModel):
    id: str
    mime_type: str
    filename: str | None = None
    sha256: str | None = None


class WhatsAppLocation(FlexibleBaseModel):
    latitude: float
    longitude: float
    name: str | None = None
    address: str | None = None
    url: str | None = None


class WhatsAppButton(FlexibleBaseModel):
    payload: str
    text: str


class WhatsAppReaction(FlexibleBaseModel):
    emoji: str
    message_id: str


class WhatsAppContactProfile(FlexibleBaseModel):
    name: str


class WhatsAppContact(FlexibleBaseModel):
    wa_id: str
    profile: WhatsAppContactProfile


class WhatsAppReferral(FlexibleBaseModel):
    source_url: str | None = None
    source_type: str | None = None
    source_id: str | None = None
    headline: str | None = None
    body: str | None = None


class WhatsAppMessage(FlexibleBaseModel):
    from_: str = Field(alias="from")
    id: str
    timestamp: str | None = None  # Made optional - MontyMobile doesn't always send it
    type: str
    text: WhatsAppText | None = None
    image: WhatsAppImage | None = None
    audio: WhatsAppAudio | None = None
    video: WhatsAppVideo | None = None
    document: WhatsAppDocument | None = None
    location: WhatsAppLocation | None = None
    contacts: list[WhatsAppContact] | None = None
    button: WhatsAppButton | None = None
    reaction: WhatsAppReaction | None = None
    referral: WhatsAppReferral | None = None


class WhatsAppStatus(FlexibleBaseModel):
    id: str
    status: str
    timestamp: str
    recipient_id: str
    conversation: dict | None = None
    pricing: dict | None = None


class WhatsAppChangeValue(FlexibleBaseModel):
    messaging_product: str
    metadata: dict
    contacts: list[WhatsAppContact] | None = None
    messages: list[WhatsAppMessage] | None = None
    statuses: list[WhatsAppStatus] | None = None


class WhatsAppChange(FlexibleBaseModel):
    field: str
    value: WhatsAppChangeValue


class WhatsAppEntry(FlexibleBaseModel):
    id: str
    changes: list[WhatsAppChange]


class WebhookRequest(FlexibleBaseModel):
    object: str
    entry: list[WhatsAppEntry]


# Testing API Models
class TestMessageRequest(BaseModel):
    phone: str
    message: str
    provider: str = "meta"
    # When set to instagram|facebook, Testing Lab exercises the Meta social processor
    # (same routing/tools/handoff as production) with a capture-only send adapter.
    channel: str | None = None
    simulate_external_send: bool = False


class TestImageRequest(BaseModel):
    phone: str
    image_url: str
    caption: str = ""
    provider: str = "meta"


class TestVoiceRequest(BaseModel):
    phone: str
    voice_text: str = ""  # Simulated transcription text
    provider: str = "montymobile"


class ProviderSwitchRequest(BaseModel):
    provider: str


# Feedback Request Model
class FeedbackRequest(BaseModel):
    conversation_id: str
    message_id: str
    user_question: str
    bot_response: str
    feedback_type: str
    correct_answer: str | None = None
    feedback_reason: str | None = None
    operator_id: str  # required — no silent operator_001 default
    language: str = "ar"


# Live Chat Models
class TakeoverRequest(BaseModel):
    conversation_id: str
    user_id: str
    operator_id: str  # required — no silent operator_001 default; callers must supply session attribution


class ReleaseRequest(BaseModel):
    conversation_id: str
    user_id: str


class MarkConversationReadRequest(BaseModel):
    conversation_id: str
    user_id: str


class SendOperatorMessageRequest(BaseModel):
    conversation_id: str
    user_id: str
    message: str
    operator_id: str
    message_type: str = "text"  # "text", "voice", "image"
    # Same key within TTL suppresses a second Firestore write + WhatsApp send (double-submit / retries).
    idempotency_key: str | None = None


class OperatorStatusRequest(BaseModel):
    operator_id: str
    status: str


class EditMessageRequest(BaseModel):
    """Request to edit a bot message content in live chat (e.g. after dislike)."""

    user_id: str
    conversation_id: str
    message_id: str
    new_content: str
