"""Apple / Google subscription verification + entitlement mapping (no secrets in code)."""

from __future__ import annotations

import os
from typing import Any, Literal

from services.entitlements_service import EntitlementStatus, apply_store_notification
from services.iap_product_catalog import subscription_product_map
from services.plan_economics import PLAN_PRICES_USD

StoreSource = Literal["apple", "google"]

# Google Play product id aliases (not Apple ASC). Kept for Android map compatibility.
_GOOGLE_PRODUCT_ALIASES: dict[str, str] = {
    "linas_ai_lite_monthly": "lite",
    "linas_ai_starter_monthly": "starter",
    "linas_ai_growth_monthly": "growth",
    "linas_ai_pro_monthly": "pro",
    "linas_ai_max_monthly": "max",
}


def _product_map() -> dict[str, str]:
    """Map store product id → plan_id (Apple catalog + Google aliases).

    Apple subscription map (incl. legacy aliases + LINAS_IAP_PRODUCT_MAP_JSON
    merge) lives in ``services.iap_product_catalog``.
    """
    mapping = dict(subscription_product_map())
    mapping.update(_GOOGLE_PRODUCT_ALIASES)
    return mapping


def iap_config_status() -> dict[str, Any]:
    from services.apple_app_store_client import iap_credentials_configured

    apple_key = iap_credentials_configured() or bool(
        (os.getenv("APPLE_IAP_SHARED_SECRET") or os.getenv("APPLE_IAP_KEY_ID") or os.getenv("APPLE_APP_STORE_KEY_ID") or "").strip()
    )
    apple_bundle = bool((os.getenv("APPLE_BUNDLE_ID") or "com.linasai.app").strip())
    google_sa = bool((os.getenv("GOOGLE_PLAY_SERVICE_ACCOUNT_JSON_PATH") or "").strip())
    google_pkg = bool((os.getenv("GOOGLE_PLAY_PACKAGE_NAME") or "com.linasai.app").strip())
    return {
        "plans": PLAN_PRICES_USD,
        "product_map": _product_map(),
        "apple": {
            "configured": bool(apple_key and apple_bundle),
            "bundle_id_env": "APPLE_BUNDLE_ID",
            "key_envs": [
                "APPLE_IAP_ISSUER_ID",
                "APPLE_IAP_KEY_ID",
                "APPLE_IAP_PRIVATE_KEY_PATH",
                "APPLE_APP_STORE_ISSUER_ID",
                "APPLE_APP_STORE_KEY_ID",
                "APPLE_APP_STORE_PRIVATE_KEY_PATH",
                "APPLE_IAP_SHARED_SECRET",
            ],
            "notification_path": "/api/entitlements/apple/notifications",
            "webhook_path": "/webhooks/apple/app-store",
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
    """Verify ASSN V2 via apple_iap_processor and return normalized fields.

    Prefer calling ``process_notification_v2`` directly from webhook routes.
    """
    from services.apple_app_store_client import iap_credentials_configured
    from services.apple_iap_processor import process_notification_v2

    if not iap_credentials_configured():
        raise PermissionError("Apple IAP credentials not configured")
    result = process_notification_v2(body)
    effect = result.get("effect") if isinstance(result.get("effect"), dict) else {}
    nested = effect.get("effect") if isinstance(effect.get("effect"), dict) else effect
    return {
        "tenant_id": nested.get("tenant_id") or result.get("tenant_id") or "",
        "product_id": "",
        "notification_type": result.get("notification_type") or "",
        "original_transaction_id": "",
        "event_id": result.get("notification_uuid") or "",
        "processor_result": result,
    }


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
            "Create auto-renewable subscriptions in group 22305050: "
            "com.linasai.subscription.{basic,plus,growth,pro,scale}.{monthly,yearly} "
            "(basic→lite, plus→starter, growth→growth, pro→pro, scale→max); "
            "Pro/Scale yearly may be Higher Price Point pending",
            "Create credit consumables: com.linasai.credits.{2500,5000,12500,25000,50000}",
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
