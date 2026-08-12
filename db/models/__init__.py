"""ORM model package for PostgreSQL SoT (WhatsApp Cloud + Customer Requests + Meta)."""

from __future__ import annotations

from db.models.base import Base
from db.models.meta_registry import (
    MetaAssetBindingRow,
    MetaBindingCredentialRow,
    MetaOAuthStateRow,
    MetaRegistryAuditEvent,
)
from db.models.requests import CustomerRequest, CustomerRequestCounter
from db.models.requests_support import (
    CustomerRequestEvent,
    CustomerRequestIdempotency,
    CustomerRequestNote,
    CustomerRequestOutbox,
)
from db.models.whatsapp_cloud import (
    WhatsAppAuditEvent,
    WhatsAppConnection,
    WhatsAppConnectionAttempt,
    WhatsAppConversation,
    WhatsAppCredential,
    WhatsAppMessage,
    WhatsAppOutboundIntent,
    WhatsAppPilotEntitlement,
    WhatsAppWebhookEvent,
)
from db.models.whatsapp_smart_followup import (
    WhatsAppSmartFollowUpEvent,
    WhatsAppSmartFollowUpJob,
    WhatsAppSmartFollowUpSequence,
    WhatsAppSmartFollowUpSettings,
    WhatsAppSmartFollowUpStep,
)

__all__ = [
    "Base",
    "CustomerRequest",
    "CustomerRequestCounter",
    "CustomerRequestEvent",
    "CustomerRequestIdempotency",
    "CustomerRequestNote",
    "CustomerRequestOutbox",
    "MetaAssetBindingRow",
    "MetaBindingCredentialRow",
    "MetaOAuthStateRow",
    "MetaRegistryAuditEvent",
    "WhatsAppAuditEvent",
    "WhatsAppConnection",
    "WhatsAppConnectionAttempt",
    "WhatsAppConversation",
    "WhatsAppCredential",
    "WhatsAppMessage",
    "WhatsAppOutboundIntent",
    "WhatsAppPilotEntitlement",
    "WhatsAppSmartFollowUpEvent",
    "WhatsAppSmartFollowUpJob",
    "WhatsAppSmartFollowUpSequence",
    "WhatsAppSmartFollowUpSettings",
    "WhatsAppSmartFollowUpStep",
    "WhatsAppWebhookEvent",
]
