"""Server-side rollout controls for WhatsApp Cloud coexistence.

All controls default OFF. Client cannot enable them.

Phase 1 (pre-Meta approval): operational flags + audited pilot entitlement rows.
Phase 2 (post-Meta approval): flip WHATSAPP_CLOUD_PUBLIC_AVAILABILITY=true — no
deploy / no mobile rebuild required. Never hardcode tenant or email bypasses.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from services.meta_app_registry import APP_A_EXPECTED_ID, APP_A_KEY

WHATSAPP_COEXISTENCE_FEATURE = "whatsapp_business_app_onboarding"
WHATSAPP_REQUIRED_SCOPES = frozenset(
    {
        "whatsapp_business_management",
        "whatsapp_business_messaging",
    }
)
# business_management only when Embedded Signup contract proves it is required.
WHATSAPP_OPTIONAL_SCOPES = frozenset({"business_management"})

GRAPH_API_HOST = "graph.facebook.com"
SUPPORTED_GRAPH_VERSIONS = frozenset({"v21.0", "v22.0", "v23.0", "v24.0"})

# Central Phase 2 public switch (config-only; default OFF).
PUBLIC_AVAILABILITY_ENV = "WHATSAPP_CLOUD_PUBLIC_AVAILABILITY"


def _truthy(name: str, default: str = "false") -> bool:
    return (os.getenv(name) or default).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class WhatsAppCloudFlags:
    """Independent default-OFF server controls (never client-controlled)."""

    connection_ui_enabled: bool
    webhook_side_effects_enabled: bool
    outbound_sends_enabled: bool
    ai_replies_enabled: bool
    history_sync_enabled: bool
    public_availability: bool
    require_pilot_entitlement: bool
    embedded_signup_config_id_configured: bool
    meta_app_id: str
    meta_app_key: str
    graph_api_version: str
    oauth_redirect_uri: str
    bridge_base_url: str


def get_whatsapp_cloud_flags() -> WhatsAppCloudFlags:
    from services.meta_app_registry import get_meta_graph_api_version

    app_id = (os.getenv("META_APP_A_ID") or os.getenv("META_APP_ID") or "").strip()
    config_id = (os.getenv("META_WHATSAPP_EMBEDDED_SIGNUP_CONFIG_ID") or "").strip()
    version = get_meta_graph_api_version()
    public_url = (os.getenv("PUBLIC_URL") or os.getenv("LINAS_PUBLIC_URL") or "").rstrip("/")
    redirect = (os.getenv("META_WHATSAPP_OAUTH_REDIRECT_URI") or "").strip()
    if not redirect and public_url:
        redirect = f"{public_url}/oauth/whatsapp/callback"
    bridge = (os.getenv("META_WHATSAPP_EMBEDDED_SIGNUP_BRIDGE_URL") or "").strip()
    if not bridge and public_url:
        bridge = f"{public_url}/integrations/whatsapp/embedded-signup"
    public_availability = _truthy(PUBLIC_AVAILABILITY_ENV)
    # Phase 1 requires audited pilot rows unless the central public switch is on.
    require_pilot = not public_availability and _truthy("WHATSAPP_CLOUD_REQUIRE_PILOT_ENTITLEMENT", "true")
    return WhatsAppCloudFlags(
        connection_ui_enabled=_truthy("WHATSAPP_CLOUD_CONNECTION_UI_ENABLED"),
        webhook_side_effects_enabled=_truthy("WHATSAPP_CLOUD_WEBHOOK_SIDE_EFFECTS_ENABLED"),
        outbound_sends_enabled=_truthy("WHATSAPP_CLOUD_OUTBOUND_SENDS_ENABLED"),
        ai_replies_enabled=_truthy("WHATSAPP_CLOUD_AI_REPLIES_ENABLED"),
        history_sync_enabled=_truthy("WHATSAPP_CLOUD_HISTORY_SYNC_ENABLED"),
        public_availability=public_availability,
        require_pilot_entitlement=require_pilot,
        embedded_signup_config_id_configured=bool(config_id),
        meta_app_id=app_id if app_id == APP_A_EXPECTED_ID else "",
        meta_app_key=APP_A_KEY,
        graph_api_version=version if version in SUPPORTED_GRAPH_VERSIONS else "v24.0",
        oauth_redirect_uri=redirect,
        bridge_base_url=bridge,
    )


def whatsapp_config_key_presence() -> dict[str, bool]:
    """Presence-only checklist for operators — never values."""

    keys = [
        "LINAS_WHATSAPP_DATABASE_URL",
        "DATABASE_URL",
        "META_CREDENTIAL_ENCRYPTION_KEY",
        "META_APP_A_ID",
        "META_APP_ID",
        "META_APP_A_SECRET",
        "META_APP_SECRET",
        "META_APP_A_WEBHOOK_VERIFY_TOKEN",
        "META_WEBHOOK_VERIFY_TOKEN",
        "META_WHATSAPP_EMBEDDED_SIGNUP_CONFIG_ID",
        "META_WHATSAPP_OAUTH_REDIRECT_URI",
        "META_WHATSAPP_EMBEDDED_SIGNUP_BRIDGE_URL",
        "WHATSAPP_CLOUD_CONNECTION_UI_ENABLED",
        "WHATSAPP_CLOUD_WEBHOOK_SIDE_EFFECTS_ENABLED",
        "WHATSAPP_CLOUD_OUTBOUND_SENDS_ENABLED",
        "WHATSAPP_CLOUD_AI_REPLIES_ENABLED",
        "WHATSAPP_CLOUD_HISTORY_SYNC_ENABLED",
        PUBLIC_AVAILABILITY_ENV,
        "WHATSAPP_CLOUD_REQUIRE_PILOT_ENTITLEMENT",
        "PUBLIC_URL",
        "MONTYMOBILE_SOURCE_NUMBER",
    ]
    return {k: bool((os.getenv(k) or "").strip()) for k in keys}
