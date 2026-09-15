"""Social channel identity, published WhatsApp contact resolve, empty founder matrix."""

from __future__ import annotations

from dataclasses import dataclass

SOCIAL_CHANNELS = {"instagram", "facebook"}

# Pending handoff TTL (seconds). Expire helper drops stale blobs from user_data.
SOCIAL_CONTACT_FLOW_TTL_SECONDS = 30 * 60

SOCIAL_BOOKING_PREFERENCES_FIELD = "social_booking_preferences"
SOCIAL_BOOKING_PREFERENCE_MEMORY_PREFIX = "social_booking_preference::v1::"

# No platform-wide WhatsApp numbers. Published CM handoff is the only SoT.
DEFAULT_SOCIAL_WHATSAPP_CONTACTS: dict[str, str] = {}


@dataclass(frozen=True)
class SocialContactScope:
    tenant_id: str
    channel: str
    business_asset_id: str
    sender_id: str


class SocialContactScopeError(RuntimeError):
    """Raised when a social handoff cannot be isolated to one business and sender."""


def _require_tenant_id(tenant_id: str | None, *, context: str = "social contact routing") -> str:
    value = str(tenant_id or "").strip()
    if not value:
        raise SocialContactScopeError(f"tenant_id required for {context}")
    return value


def _tenant_id_from_user_data(user_data: dict) -> str:
    raw = user_data.get("tenant_id") or user_data.get("tenantId") or user_data.get("workspace_id")
    return _require_tenant_id(str(raw) if raw is not None else None)


def is_social_channel(channel: str | None) -> bool:
    return str(channel or "").strip().lower() in SOCIAL_CHANNELS


def resolve_social_whatsapp_number(env_name: str, *, tenant_id: str) -> str | None:
    """Resolve public WhatsApp contact from published CM handoff only.

    Missing tenant raises. Missing published contact returns None (no founder matrix).
    """
    tenant = _require_tenant_id(tenant_id, context="social WhatsApp contact resolution")
    contact_id = env_name.strip().lower()

    from services.ai_setup.constants import tenant_uses_cm_runtime

    if not tenant_uses_cm_runtime(tenant):
        return None
    try:
        from services.ai_setup.schemas import HandoffPolicy
        from services.ai_setup.version_store import load_published_content

        _pointer, sections = load_published_content(tenant)
        policy = HandoffPolicy.model_validate(sections.get("handoff") or {})
        for contact in policy.contacts:
            if contact.id != contact_id:
                continue
            dtype, value = contact.resolved_destination()
            if not value:
                return None
            if dtype in {"whatsapp", "phone"}:
                return value
            return None
    except Exception as exc:
        print(f"[social_contact_routing] published handoff resolve failed for {env_name}: {exc}")
        return None
    return None


def clear_social_contact_flow(user_data: dict) -> None:
    """Clear legacy and channel-scoped pending social handoff state."""
    user_data.pop("social_contact_flow", None)
    for key in list(user_data.keys()):
        if str(key).startswith("social_contact_flow::"):
            user_data.pop(key, None)
