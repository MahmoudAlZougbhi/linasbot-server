# -*- coding: utf-8 -*-
"""
Models module: Pydantic models for WhatsApp messages and requests
Defines all request/response models for API endpoints and webhook processing.
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Union, Dict, Any
import json


# Base model to allow extra fields without error
class FlexibleBaseModel(BaseModel):
    class Config:
        extra = 'ignore'


# WhatsApp Message Content Types
class WhatsAppText(FlexibleBaseModel):
    body: str


class WhatsAppImage(FlexibleBaseModel):
    id: str
    mime_type: str
    sha256: Optional[str] = None


class WhatsAppAudio(FlexibleBaseModel):
    id: str
    mime_type: str
    voice: Optional[bool] = None


class WhatsAppVideo(FlexibleBaseModel):
    id: str
    mime_type: str
    sha256: Optional[str] = None


class WhatsAppDocument(FlexibleBaseModel):
    id: str
    mime_type: str
    filename: Optional[str] = None
    sha256: Optional[str] = None


class WhatsAppLocation(FlexibleBaseModel):
    latitude: float
    longitude: float
    name: Optional[str] = None
    address: Optional[str] = None
    url: Optional[str] = None


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
    source_url: Optional[str] = None
    source_type: Optional[str] = None
    source_id: Optional[str] = None
    headline: Optional[str] = None
    body: Optional[str] = None


class WhatsAppMessage(FlexibleBaseModel):
    from_: str = Field(alias='from')
    id: str
    timestamp: Optional[str] = None  # Made optional - MontyMobile doesn't always send it
    type: str
    text: Optional[WhatsAppText] = None
    image: Optional[WhatsAppImage] = None
    audio: Optional[WhatsAppAudio] = None
    video: Optional[WhatsAppVideo] = None
    document: Optional[WhatsAppDocument] = None
    location: Optional[WhatsAppLocation] = None
    contacts: Optional[List[WhatsAppContact]] = None
    button: Optional[WhatsAppButton] = None
    reaction: Optional[WhatsAppReaction] = None
    referral: Optional[WhatsAppReferral] = None


class WhatsAppStatus(FlexibleBaseModel):
    id: str
    status: str
    timestamp: str
    recipient_id: str
    conversation: Optional[dict] = None
    pricing: Optional[dict] = None


class WhatsAppChangeValue(FlexibleBaseModel):
    messaging_product: str
    metadata: dict
    contacts: Optional[List[WhatsAppContact]] = None
    messages: Optional[List[WhatsAppMessage]] = None
    statuses: Optional[List[WhatsAppStatus]] = None


class WhatsAppChange(FlexibleBaseModel):
    field: str
    value: WhatsAppChangeValue


class WhatsAppEntry(FlexibleBaseModel):
    id: str
    changes: List[WhatsAppChange]


class WebhookRequest(FlexibleBaseModel):
    object: str
    entry: List[WhatsAppEntry]


# Testing API Models
class TestMessageRequest(BaseModel):
    phone: str
    message: str
    provider: str = "meta"


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
    correct_answer: Optional[str] = None
    feedback_reason: Optional[str] = None
    operator_id: Optional[str] = "operator_001"
    language: str = "ar"


# Live Chat Models
class TakeoverRequest(BaseModel):
    conversation_id: str
    user_id: str
    operator_id: str = "operator_001"


class ReleaseRequest(BaseModel):
    conversation_id: str
    user_id: str


class SendOperatorMessageRequest(BaseModel):
    conversation_id: str
    user_id: str
    message: str
    operator_id: str
    message_type: str = "text"  # "text", "voice", "image"


class OperatorStatusRequest(BaseModel):
    operator_id: str
    status: str
