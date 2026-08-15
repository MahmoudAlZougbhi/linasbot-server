"""ORM model package for PostgreSQL SoT (WhatsApp Cloud + Customer Requests + Meta + Apple)."""

from __future__ import annotations

from db.models.apple_billing import (
    AppleAppAccountTokenRow,
    AppleCreditGrantRow,
    AppleNotificationEventRow,
    AppleTransactionRow,
    AuthExternalIdentityRow,
)
from db.models.base import Base
from db.models.billing_auth import (
    AdminCreditIdempotencyRow,
    AuthEmailTokenRow,
    MobileRefreshTokenRow,
    StripeProcessedEventRow,
    TokenWalletLedgerRow,
    TokenWalletRow,
)
from db.models.credit_entitlements import (
    CreditBalanceRow,
    CreditLedgerEntryRow,
    EntitlementProcessedEventRow,
    TenantEntitlementRow,
)
from db.models.meta_registry import (
    MetaAssetBindingRow,
    MetaBindingCredentialRow,
    MetaOAuthStateRow,
    MetaRegistryAuditEvent,
)
from db.models.products import (
    Product,
    ProductConversationContext,
    ProductImage,
    ProductLink,
    ProductSentMessage,
)
from db.models.tenant_services import ServiceOption, TenantService
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
    "AdminCreditIdempotencyRow",
    "AppleAppAccountTokenRow",
    "AppleCreditGrantRow",
    "AppleNotificationEventRow",
    "AppleTransactionRow",
    "AuthEmailTokenRow",
    "AuthExternalIdentityRow",
    "Base",
    "CreditBalanceRow",
    "CreditLedgerEntryRow",
    "CustomerRequest",
    "CustomerRequestCounter",
    "CustomerRequestEvent",
    "CustomerRequestIdempotency",
    "CustomerRequestNote",
    "CustomerRequestOutbox",
    "EntitlementProcessedEventRow",
    "MetaAssetBindingRow",
    "MetaBindingCredentialRow",
    "MetaOAuthStateRow",
    "MetaRegistryAuditEvent",
    "MobileRefreshTokenRow",
    "Product",
    "ProductConversationContext",
    "ProductImage",
    "ProductLink",
    "ProductSentMessage",
    "ServiceOption",
    "TenantService",
    "StripeProcessedEventRow",
    "TenantEntitlementRow",
    "TokenWalletLedgerRow",
    "TokenWalletRow",
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
