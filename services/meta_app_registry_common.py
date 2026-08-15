"""Shared Meta app registry types, configs, and helpers (LOC split)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
from dataclasses import dataclass
from typing import Any, Literal, cast

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

APP_A_KEY = "linas_first_party"
APP_B_KEY = "saas_tech_provider"
APP_A_EXPECTED_ID = "2963733803971681"
RETIRED_APP_ID = "1784792718776344"
# Facebook Connect / Manage Meta Access — Pages-only Login Configuration.
FACEBOOK_ONLY_LOGIN_CONFIG_ID_DEFAULT = "1369663304545819"
LINAS_PAGE_ID = "378696005334409"
LINAS_INSTAGRAM_ACCOUNT_ID = "17841413184256533"
REGISTRY_SCHEMA_VERSION = 1

MetaChannel = Literal["facebook", "instagram"]
MetaAppClassification = Literal["own_business", "tech_provider"]
BindingStatus = Literal["active", "inactive", "testing", "disconnected"]
AuthFlow = Literal["facebook_login", "instagram_login"]

META_COMMON_MESSAGING_SCOPES = frozenset(
    {
        "pages_show_list",
        "pages_manage_metadata",
        "pages_read_engagement",
    }
)
META_CHANNEL_SCOPES: dict[MetaChannel, frozenset[str]] = {
    "facebook": META_COMMON_MESSAGING_SCOPES | {"pages_messaging"},
    "instagram": META_COMMON_MESSAGING_SCOPES | {"instagram_basic", "instagram_manage_messages"},
}
META_COMMENT_SCOPES: dict[MetaChannel, frozenset[str]] = {
    "facebook": frozenset({"pages_read_user_content", "pages_manage_engagement"}),
    "instagram": frozenset({"instagram_manage_comments"}),
}
# Extra scopes requested on Facebook-only Business Login (Pages). Not required for
# legacy Page messaging activation checks, but allowed on stored credentials.
META_FACEBOOK_LOGIN_EXTRA_SCOPES = frozenset({"business_management"})
META_PUBLISH_SCOPES: dict[MetaChannel, frozenset[str]] = {
    "facebook": frozenset({"pages_manage_posts"}),
    "instagram": frozenset({"instagram_content_publish"}),
}
META_FORBIDDEN_SCOPES = frozenset(
    {
        "pages_manage_ads",
        "ads_management",
        "ads_read",
        "catalog_management",
        "commerce_account_manage_orders",
        "whatsapp_business_management",
        "whatsapp_business_messaging",
    }
)


class MetaRegistryError(RuntimeError):
    """Base class for registry failures safe to report by type only."""


class MetaRegistryNotConfiguredError(MetaRegistryError):
    pass


class MetaBindingConflictError(MetaRegistryError):
    pass


class MetaBindingNotFoundError(MetaRegistryError):
    pass


class MetaCredentialError(MetaRegistryError):
    pass


class MetaOAuthStateError(MetaRegistryError):
    pass


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def meta_multi_app_registry_enabled() -> bool:
    return _truthy(os.getenv("META_MULTI_APP_REGISTRY_ENABLED"))


def _normalized_graph_version(value: str | None) -> str:
    version = (value or "v24.0").strip()
    return version if version.startswith("v") else f"v{version}"


def get_meta_graph_api_version() -> str:
    return _normalized_graph_version(os.getenv("META_GRAPH_API_VERSION"))


def _app_b_linas_cutover_allowed() -> bool:
    return _truthy(os.getenv("META_APP_B_LINAS_CUTOVER_APPROVED"))


def normalize_meta_tenant_id(value: str) -> str:
    """Return the canonical tenant key used in bindings and state namespaces."""

    tenant = str(value or "").strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", tenant):
        raise MetaBindingConflictError("tenant identifier is invalid")
    return tenant


def _bindings_share_exclusive_asset(left: MetaAssetBinding, right: MetaAssetBinding) -> bool:
    if left.tenant_id != right.tenant_id or left.channel != right.channel or left.asset_id != right.asset_id:
        return False
    if left.channel == "instagram":
        return left.auth_flow == right.auth_flow
    return True


def binding_asset_key(
    tenant_id: str,
    app_key: str,
    channel: str,
    asset_id: str,
    auth_flow: AuthFlow = "facebook_login",
) -> str:
    tenant = normalize_meta_tenant_id(tenant_id)
    asset = str(asset_id or "").strip()
    if channel == "instagram":
        return f"{tenant}:{app_key}:{channel}:{auth_flow}:{asset}"
    return f"{tenant}:{app_key}:{channel}:{asset}"


def authorized_meta_user_id_hash(meta_user_id: str) -> str:
    raw = str(meta_user_id or "").strip()
    if not raw:
        return ""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def mask_asset_id(asset_id: str) -> str:
    raw = str(asset_id or "").strip()
    if len(raw) <= 6:
        return "***"
    return f"{raw[:3]}…{raw[-3:]}"


@dataclass(frozen=True)
class MetaAppConfig:
    key: str
    app_id: str
    app_secret: str
    verify_token: str
    graph_api_version: str
    classification: MetaAppClassification
    oauth_config_id: str = ""
    advanced_access_approved: bool = False
    enabled: bool = False

    def public_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "app_id": self.app_id,
            "classification": self.classification,
            "graph_api_version": self.graph_api_version,
            "oauth_configured": bool(self.oauth_config_id),
            "advanced_access_approved": self.advanced_access_approved,
            "credentials_configured": bool(self.app_secret and self.verify_token),
            "enabled": self.enabled,
        }


def get_meta_app_configs() -> dict[str, MetaAppConfig]:
    """Load the two allowlisted Meta apps without exposing secret values."""

    graph_version = get_meta_graph_api_version()
    app_a_id = (os.getenv("META_APP_A_ID") or os.getenv("META_APP_ID") or "").strip()
    app_a_secret = (os.getenv("META_APP_A_SECRET") or os.getenv("META_APP_SECRET") or "").strip()
    app_a_verify = (
        os.getenv("META_APP_A_WEBHOOK_VERIFY_TOKEN") or os.getenv("META_WEBHOOK_VERIFY_TOKEN") or ""
    ).strip()
    app_a = MetaAppConfig(
        key=APP_A_KEY,
        app_id=app_a_id,
        app_secret=app_a_secret,
        verify_token=app_a_verify,
        graph_api_version=graph_version,
        classification="own_business",
        oauth_config_id=(
            os.getenv("META_APP_A_FACEBOOK_LOGIN_CONFIG_ID") or FACEBOOK_ONLY_LOGIN_CONFIG_ID_DEFAULT
        ).strip(),
        advanced_access_approved=_truthy(os.getenv("META_APP_A_ADVANCED_ACCESS_APPROVED")),
        enabled=bool(
            app_a_id and app_a_id == APP_A_EXPECTED_ID and app_a_id != RETIRED_APP_ID and app_a_secret and app_a_verify
        ),
    )

    app_b_id = (os.getenv("META_APP_B_ID") or "").strip()
    app_b_secret = (os.getenv("META_APP_B_SECRET") or "").strip()
    app_b_verify = (os.getenv("META_APP_B_WEBHOOK_VERIFY_TOKEN") or "").strip()
    app_b = MetaAppConfig(
        key=APP_B_KEY,
        app_id=app_b_id,
        app_secret=app_b_secret,
        verify_token=app_b_verify,
        graph_api_version=graph_version,
        classification="tech_provider",
        oauth_config_id=(os.getenv("META_APP_B_LOGIN_CONFIG_ID") or "").strip(),
        advanced_access_approved=_truthy(os.getenv("META_APP_B_ADVANCED_ACCESS_APPROVED")),
        enabled=bool(
            app_b_id
            and app_b_id.isdigit()
            and app_b_id not in {RETIRED_APP_ID, APP_A_EXPECTED_ID}
            and app_b_secret
            and app_b_verify
        ),
    )
    return {APP_A_KEY: app_a, APP_B_KEY: app_b}


def identify_signed_meta_app(raw_body: bytes, signature_header: str | None) -> MetaAppConfig | None:
    """Return the single configured app whose secret authenticates ``raw_body``.

    Every candidate is explicitly allowlisted by registry key.  Ambiguous signatures
    are rejected rather than falling back to an unrestricted secondary secret.
    """

    if not raw_body or not signature_header or not signature_header.startswith("sha256="):
        return None
    received = signature_header[len("sha256=") :].strip().lower()
    matches: list[MetaAppConfig] = []
    for config in get_meta_app_configs().values():
        if not config.enabled:
            continue
        expected = hmac.new(config.app_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
        if hmac.compare_digest(received, expected):
            matches.append(config)
    return matches[0] if len(matches) == 1 else None


def verify_any_meta_challenge_token(candidate: str | None) -> bool:
    """Constant-time verification against only the two configured app tokens."""

    supplied = candidate or ""
    matched = False
    for config in get_meta_app_configs().values():
        if config.enabled and config.verify_token:
            matched = hmac.compare_digest(supplied, config.verify_token) or matched
    return matched


class MetaCredentialCipher:
    """AES-256-GCM envelope for tenant tokens persisted by the registry."""

    def __init__(self, master_secret: str):
        secret = (master_secret or "").strip()
        if len(secret) < 32:
            raise MetaRegistryNotConfiguredError("META_CREDENTIAL_ENCRYPTION_KEY must be at least 32 characters")
        key = hashlib.sha256(b"linas-meta-registry-v1\x00" + secret.encode("utf-8")).digest()
        self._aead = AESGCM(key)

    def seal(self, payload: dict[str, Any], *, aad: str) -> str:
        nonce = secrets.token_bytes(12)
        plaintext = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        ciphertext = self._aead.encrypt(nonce, plaintext, aad.encode("utf-8"))
        envelope = base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii").rstrip("=")
        return f"v1.{envelope}"

    def open(self, envelope: str, *, aad: str) -> dict[str, Any]:
        try:
            version, encoded = envelope.split(".", 1)
            if version != "v1":
                raise ValueError("unsupported envelope")
            raw = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
            plaintext = self._aead.decrypt(raw[:12], raw[12:], aad.encode("utf-8"))
            decoded = json.loads(plaintext)
            if not isinstance(decoded, dict):
                raise ValueError("credential payload is not an object")
            return cast(dict[str, Any], decoded)
        except Exception as exc:
            raise MetaCredentialError("stored Meta credential could not be decrypted") from exc


@dataclass(frozen=True)
class MetaAssetBinding:
    binding_id: str
    tenant_id: str
    channel: MetaChannel
    asset_id: str
    page_id: str
    instagram_account_id: str
    app_key: str
    credential_id: str
    status: BindingStatus
    generation: int
    created_at: float
    updated_at: float
    previous_binding_id: str = ""
    page_name: str = ""
    instagram_username: str = ""
    authorized_meta_user_id_hash: str = ""
    superseded_by_binding_id: str = ""
    auth_flow: AuthFlow = "facebook_login"
    webhook_subscription_status: str = "unknown"
    webhook_subscribed_fields: tuple[str, ...] = ()
    webhook_subscription_error: str = ""
    webhook_subscription_checked_at: float = 0.0

    @property
    def active(self) -> bool:
        return self.status == "active"

    @property
    def asset_key(self) -> str:
        return binding_asset_key(
            self.tenant_id,
            self.app_key,
            self.channel,
            self.asset_id,
            self.auth_flow,
        )

    @property
    def instagram_login_ready(self) -> bool:
        if self.auth_flow != "instagram_login":
            return self.active
        from services.meta_instagram_login_subscription import REQUIRED_DM_SUBSCRIPTION_FIELDS

        if self.webhook_subscription_status not in {"ready", "partial"}:
            return False
        return self.active and REQUIRED_DM_SUBSCRIPTION_FIELDS.issubset(self.webhook_subscribed_fields)

    @property
    def visible_in_dashboard(self) -> bool:
        return not self.superseded_by_binding_id

    def public_dict(self) -> dict[str, Any]:
        return {
            "binding_id": self.binding_id,
            "tenant_id": self.tenant_id,
            "channel": self.channel,
            "asset_id": self.asset_id,
            "asset_id_masked": mask_asset_id(self.asset_id),
            "page_id": self.page_id,
            "page_id_masked": mask_asset_id(self.page_id),
            "instagram_account_id": self.instagram_account_id,
            "instagram_account_id_masked": mask_asset_id(self.instagram_account_id),
            "page_name": self.page_name,
            "instagram_username": self.instagram_username,
            "app_key": self.app_key,
            "app_label": "Lina Meta app" if self.app_key == APP_A_KEY else "Legacy provider",
            "status": self.status,
            "generation": self.generation,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "connected_at": self.created_at,
            "previous_binding_id": self.previous_binding_id,
            "authorized_meta_user_id_hash": self.authorized_meta_user_id_hash,
            "superseded_by_binding_id": self.superseded_by_binding_id,
            "auth_flow": self.auth_flow,
            **(
                {
                    "webhook_subscription": {
                        "status": self.webhook_subscription_status,
                        "subscribed_fields": list(self.webhook_subscribed_fields),
                        "error": self.webhook_subscription_error,
                        "checked_at": self.webhook_subscription_checked_at,
                        "ready_for_dm": self.instagram_login_ready,
                        "ready_for_comments": "comments" in self.webhook_subscribed_fields,
                    }
                }
                if self.auth_flow == "instagram_login"
                else {}
            ),
            "asset_key": self.asset_key,
        }


@dataclass(frozen=True)
class MetaBindingCredential:
    access_token: str
    token_app_id: str
    token_profile_id: str
    scopes: tuple[str, ...]
    expires_at: int | None = None
    authorized_meta_user_id: str = ""
    auth_flow: AuthFlow = "facebook_login"
    declined_scopes: tuple[str, ...] = ()
    authorization_started_at: float = 0.0

    def as_secret_dict(self) -> dict[str, Any]:
        return {
            "access_token": self.access_token,
            "token_app_id": self.token_app_id,
            "token_profile_id": self.token_profile_id,
            "scopes": list(self.scopes),
            "expires_at": self.expires_at,
            "authorized_meta_user_id": self.authorized_meta_user_id,
            "auth_flow": self.auth_flow,
            "declined_scopes": list(self.declined_scopes),
            "authorization_started_at": self.authorization_started_at,
        }
