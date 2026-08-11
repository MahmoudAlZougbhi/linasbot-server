"""Apple / Google subscription verification + entitlement mapping (no secrets in code)."""

from __future__ import annotations

import json
import os
from typing import Any, Literal

from services.entitlements_service import EntitlementStatus, apply_store_notification
from services.plan_economics import PLAN_PRICES_USD

StoreSource = Literal["apple", "google"]


# Product IDs must be created in App Store Connect / Play Console — mapped here by env.
def _product_map() -> dict[str, str]:
    """Map store product id → plan_id. Override via LINAS_IAP_PRODUCT_MAP_JSON."""
    raw = (os.getenv("LINAS_IAP_PRODUCT_MAP_JSON") or "").strip()
    if raw:
        data = json.loads(raw)
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items()}
    # Defaults — placeholders until store products exist (not secrets).
    return {
        "com.linasai.app.lite.monthly": "lite",
        "com.linasai.app.starter.monthly": "starter",
        "com.linasai.app.growth.monthly": "growth",
        "com.linasai.app.pro.monthly": "pro",
        "com.linasai.app.max.monthly": "max",
        "linas_ai_lite_monthly": "lite",
        "linas_ai_starter_monthly": "starter",
        "linas_ai_growth_monthly": "growth",
        "linas_ai_pro_monthly": "pro",
        "linas_ai_max_monthly": "max",
    }


def iap_config_status() -> dict[str, Any]:
    apple_key = bool((os.getenv("APPLE_IAP_SHARED_SECRET") or os.getenv("APPLE_APP_STORE_KEY_ID") or "").strip())
    apple_bundle = bool((os.getenv("APPLE_BUNDLE_ID") or "com.linasai.app").strip())
    google_sa = bool((os.getenv("GOOGLE_PLAY_SERVICE_ACCOUNT_JSON_PATH") or "").strip())
    google_pkg = bool((os.getenv("GOOGLE_PLAY_PACKAGE_NAME") or "com.linasai.app").strip())
    return {
        "plans": PLAN_PRICES_USD,
        "product_map": _product_map(),
        "apple": {
            "configured": apple_key and apple_bundle,
            "bundle_id_env": "APPLE_BUNDLE_ID",
            "key_envs": [
                "APPLE_IAP_SHARED_SECRET",
                "APPLE_APP_STORE_KEY_ID",
                "APPLE_APP_STORE_ISSUER_ID",
                "APPLE_APP_STORE_PRIVATE_KEY_PATH",
            ],
            "notification_path": "/api/entitlements/apple/notifications",
            "sandbox_verified": False,
        },
        "google": {
            "configured": google_sa and google_pkg,
            "package_env": "GOOGLE_PLAY_PACKAGE_NAME",
            "sa_path_env": "GOOGLE_PLAY_SERVICE_ACCOUNT_JSON_PATH",
            "notification_path": "/api/entitlements/google/notifications",
            "sandbox_verified": False,
        },
        "code_ready": True,
        "purchase_ready": False,
        "note": "purchase_ready stays false until sandbox verification succeeds with real store credentials.",
    }


def map_product_to_plan(product_id: str) -> str:
    plan = _product_map().get(product_id)
    if not plan or plan not in PLAN_PRICES_USD:
        raise ValueError(f"Unmapped store product: {product_id}")
    return plan


def normalize_apple_status(notification_type: str) -> EntitlementStatus:
    t = (notification_type or "").upper()
    if t in {"DID_RENEW", "SUBSCRIBED", "OFFER_REDEEMED", "INITIAL_BUY"}:
        return "active"
    if t in {"DID_FAIL_TO_RENEW", "GRACE_PERIOD_EXPIRED"}:
        return "grace"
    if t in {"EXPIRED"}:
        return "expired"
    if t in {"REVOKE", "REFUND"}:
        return "refunded"
    if t in {"CANCEL", "DID_CHANGE_RENEWAL_STATUS"}:
        return "canceled"
    return "active"


def normalize_google_status(subscription_state: str) -> EntitlementStatus:
    s = (subscription_state or "").upper()
    if "ACTIVE" in s or s in {"SUBSCRIPTION_STATE_ACTIVE"}:
        return "active"
    if "IN_GRACE" in s:
        return "grace"
    if "EXPIRED" in s:
        return "expired"
    if "REVOKED" in s:
        return "revoked"
    if "CANCELED" in s or "CANCELLED" in s:
        return "canceled"
    return "active"


def apply_normalized_notification(
    *,
    tenant_id: str,
    source: StoreSource,
    product_id: str,
    status: EntitlementStatus,
    original_transaction_id: str,
    event_id: str,
) -> dict[str, Any]:
    plan_id = map_product_to_plan(product_id)
    return apply_store_notification(
        tenant_id=tenant_id,
        plan_id=plan_id,  # type: ignore[arg-type]
        status=status,
        source=source,
        original_transaction_id=original_transaction_id,
        idempotency_key=f"{source}:{event_id}",
    )


def verify_apple_notification_payload(body: dict[str, Any]) -> dict[str, Any]:
    """Parse Apple ASSN v2-style payload fields we need.

    Full JWS cryptographic verification requires APPLE_APP_STORE_* credentials.
    Without them this raises — never silently accept.
    """
    if not iap_config_status()["apple"]["configured"]:
        raise PermissionError("Apple IAP credentials not configured")
    # When credentials exist, replace with real JWS verify. Until then fail closed.
    raise PermissionError(
        "Apple notification signature verification not yet bound to production keys — "
        "configure APPLE_APP_STORE_* then enable verifier"
    )


def verify_google_notification_payload(body: dict[str, Any]) -> dict[str, Any]:
    if not iap_config_status()["google"]["configured"]:
        raise PermissionError("Google Play credentials not configured")
    raise PermissionError(
        "Google Play RTDN verification not yet bound to production service account — "
        "configure GOOGLE_PLAY_SERVICE_ACCOUNT_JSON_PATH then enable verifier"
    )


def external_store_checklist() -> dict[str, Any]:
    return {
        "apple": [
            "Create App ID com.linasai.app in App Store Connect",
            "Create auto-renewable subscriptions: lite/starter/growth/pro/max monthly at $9.99/$25/$59/$109/$259",
            "Configure App Store Server Notifications V2 URL: https://linasaibot.com/api/entitlements/apple/notifications",
            "Create API key (Issuer ID, Key ID, .p8) and set server env APPLE_APP_STORE_*",
            "Run sandbox purchase for each SKU; confirm entitlement active + renewal + cancel",
        ],
        "google": [
            "Create Play app com.linasai.app",
            "Create subscription products matching LINAS_IAP_PRODUCT_MAP_JSON",
            "Enable Google Play Developer API + Real-time developer notifications to Pub/Sub",
            "Create service account with Android Publisher access; set GOOGLE_PLAY_SERVICE_ACCOUNT_JSON_PATH on server",
            "Point RTDN push/bridge to https://linasaibot.com/api/entitlements/google/notifications",
            "Run license-tester purchase for each SKU; confirm entitlement active + cancel",
        ],
    }
