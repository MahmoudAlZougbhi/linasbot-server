"""Instagram Login capability readiness and dual-flow binding selection."""

from __future__ import annotations

import time
from typing import Literal

from services.meta_app_registry import (
    META_COMMENT_SCOPES,
    MetaAppRegistry,
    MetaAssetBinding,
    MetaBindingCredential,
    get_meta_app_registry,
)
from services.meta_instagram_login_subscription import (
    COMMENTS_SUBSCRIPTION_FIELD,
    REQUIRED_DM_SUBSCRIPTION_FIELDS,
)

MetaCapability = Literal["dm", "comments", "publish", "profile"]

_INSTAGRAM_LOGIN_DM_SCOPE = "instagram_business_manage_messages"
_INSTAGRAM_LOGIN_COMMENTS_SCOPE = "instagram_business_manage_comments"
_INSTAGRAM_LOGIN_PUBLISH_SCOPE = "instagram_business_content_publish"
_INSTAGRAM_LOGIN_BASIC_SCOPE = "instagram_business_basic"


def _verified_fields(binding: MetaAssetBinding) -> frozenset[str]:
    return frozenset(binding.webhook_subscribed_fields)


def binding_ready_for_dm(binding: MetaAssetBinding, credential: MetaBindingCredential) -> bool:
    if binding.status != "active":
        return False
    if binding.channel == "facebook":
        return "pages_messaging" in credential.scopes
    if binding.channel != "instagram":
        return False
    if binding.auth_flow == "instagram_login":
        return _INSTAGRAM_LOGIN_DM_SCOPE in credential.scopes and REQUIRED_DM_SUBSCRIPTION_FIELDS.issubset(
            _verified_fields(binding)
        )
    return "instagram_manage_messages" in credential.scopes


def binding_ready_for_comments(binding: MetaAssetBinding, credential: MetaBindingCredential) -> bool:
    if binding.status != "active":
        return False
    if binding.channel == "facebook":
        return META_COMMENT_SCOPES["facebook"].issubset(credential.scopes)
    if binding.channel != "instagram":
        return False
    if binding.auth_flow == "instagram_login":
        if _INSTAGRAM_LOGIN_COMMENTS_SCOPE not in credential.scopes:
            return False
        return COMMENTS_SUBSCRIPTION_FIELD in _verified_fields(binding)
    return "instagram_manage_comments" in credential.scopes


def binding_ready_for_publish(binding: MetaAssetBinding, credential: MetaBindingCredential) -> bool:
    if binding.status != "active":
        return False
    if binding.auth_flow == "instagram_login" and binding.channel == "instagram":
        return _INSTAGRAM_LOGIN_PUBLISH_SCOPE in credential.scopes
    if binding.channel == "facebook":
        return "pages_manage_posts" in credential.scopes
    if binding.channel == "instagram":
        return "instagram_content_publish" in credential.scopes
    return False


def binding_ready_for_profile(binding: MetaAssetBinding, credential: MetaBindingCredential) -> bool:
    if binding.status != "active":
        return False
    if binding.auth_flow == "instagram_login" and binding.channel == "instagram":
        return _INSTAGRAM_LOGIN_BASIC_SCOPE in credential.scopes
    if binding.channel == "instagram":
        return "instagram_basic" in credential.scopes
    return True


def binding_ready_for_capability(
    binding: MetaAssetBinding,
    capability: MetaCapability,
    *,
    credential: MetaBindingCredential | None = None,
    registry: MetaAppRegistry | None = None,
) -> bool:
    current_registry = registry or get_meta_app_registry()
    resolved = credential or current_registry.get_credential(binding)
    if capability == "dm":
        return binding_ready_for_dm(binding, resolved)
    if capability == "comments":
        return binding_ready_for_comments(binding, resolved)
    if capability == "publish":
        return binding_ready_for_publish(binding, resolved)
    return binding_ready_for_profile(binding, resolved)


def select_instagram_binding_for_capability(
    bindings: list[MetaAssetBinding],
    capability: MetaCapability,
    *,
    registry: MetaAppRegistry | None = None,
) -> MetaAssetBinding | None:
    """Prefer direct Instagram Login when ready for the capability; otherwise page-linked."""

    current_registry = registry or get_meta_app_registry()
    candidates = [binding for binding in bindings if binding.channel == "instagram" and binding.status == "active"]
    for preferred_flow in ("instagram_login", "facebook_login"):
        for binding in candidates:
            if binding.auth_flow != preferred_flow:
                continue
            try:
                credential = current_registry.get_credential(binding)
            except Exception:
                continue
            if binding_ready_for_capability(binding, capability, credential=credential, registry=current_registry):
                return binding
    return None


def instagram_login_needs_subscription_work(
    binding: MetaAssetBinding,
    credential: MetaBindingCredential,
) -> bool:
    if binding.auth_flow != "instagram_login" or binding.status != "active":
        return False
    verified = _verified_fields(binding)
    if not REQUIRED_DM_SUBSCRIPTION_FIELDS.issubset(verified):
        return True
    if _INSTAGRAM_LOGIN_COMMENTS_SCOPE in credential.scopes and COMMENTS_SUBSCRIPTION_FIELD not in verified:
        return True
    return binding.webhook_subscription_status in {"pending", "failed", "unknown"}


_SUBSCRIPTION_RETRY_BACKOFF_SECONDS: dict[str, float] = {
    "unknown": 0.0,
    "pending": 30.0,
    "partial": 120.0,
    "failed": 300.0,
}


def instagram_login_subscription_retry_eligible(
    binding: MetaAssetBinding,
    credential: MetaBindingCredential,
    *,
    now: float | None = None,
) -> bool:
    if not instagram_login_needs_subscription_work(binding, credential):
        return False
    last_checked = binding.webhook_subscription_checked_at
    if last_checked <= 0:
        return True
    delay = _SUBSCRIPTION_RETRY_BACKOFF_SECONDS.get(binding.webhook_subscription_status, 300.0)
    current = time.time() if now is None else now
    return current - last_checked >= delay


def facebook_login_binding_superseded_for_capability(
    binding: MetaAssetBinding,
    capability: MetaCapability,
    *,
    registry: MetaAppRegistry | None = None,
) -> bool:
    """Defer page-linked Instagram handling when direct Instagram Login owns the capability."""

    if binding.auth_flow != "facebook_login" or binding.channel != "instagram":
        return False
    current_registry = registry or get_meta_app_registry()
    for other in current_registry.list_bindings(include_inactive=False):
        if other.auth_flow != "instagram_login" or other.channel != "instagram":
            continue
        if other.status != "active":
            continue
        if other.tenant_id != binding.tenant_id or other.asset_id != binding.asset_id:
            continue
        try:
            other_credential = current_registry.get_credential(other)
        except Exception:
            continue
        if binding_ready_for_capability(
            other,
            capability,
            credential=other_credential,
            registry=current_registry,
        ):
            return True
    return False
