"""Canonical Apple IAP product maps (server owns quantities / plan mapping).

ASC product_id → Linas plan_id alignment is by ascending price:
  basic → lite, plus → starter, growth → growth, pro → pro, scale → max.

Pro/Scale yearly may still be Higher Price Point pending in ASC — they remain
mapped here so verify/apply paths stay consistent once products go live.

Optional env ``LINAS_IAP_PRODUCT_MAP_JSON`` merges/overrides the subscription
map only (not credit consumables). Never put secrets in this module.
"""

from __future__ import annotations

import json
import os

APPLE_BUNDLE_ID = "com.linasai.app"
SUBSCRIPTION_GROUP_ID = "22305050"

# Canonical ASC auto-renewable subscription product IDs → Linas plan_id.
_CANONICAL_SUBSCRIPTION_PRODUCTS: dict[str, str] = {
    "com.linasai.subscription.basic.monthly": "lite",
    "com.linasai.subscription.basic.yearly": "lite",
    "com.linasai.subscription.plus.monthly": "starter",
    "com.linasai.subscription.plus.yearly": "starter",
    "com.linasai.subscription.growth.monthly": "growth",
    "com.linasai.subscription.growth.yearly": "growth",
    "com.linasai.subscription.pro.monthly": "pro",
    "com.linasai.subscription.pro.yearly": "pro",
    "com.linasai.subscription.scale.monthly": "max",
    "com.linasai.subscription.scale.yearly": "max",
}

# Legacy placeholders kept as aliases for backward compatibility.
_LEGACY_SUBSCRIPTION_ALIASES: dict[str, str] = {
    "com.linasai.app.lite.monthly": "lite",
    "com.linasai.app.starter.monthly": "starter",
    "com.linasai.app.growth.monthly": "growth",
    "com.linasai.app.pro.monthly": "pro",
    "com.linasai.app.max.monthly": "max",
}

_CREDIT_PRODUCTS: dict[str, int] = {
    "com.linasai.credits.2500": 2500,
    "com.linasai.credits.5000": 5000,
    "com.linasai.credits.12500": 12500,
    "com.linasai.credits.25000": 25000,
    "com.linasai.credits.50000": 50000,
}


def _env_subscription_overrides() -> dict[str, str]:
    raw = (os.getenv("LINAS_IAP_PRODUCT_MAP_JSON") or "").strip()
    if not raw:
        return {}
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("LINAS_IAP_PRODUCT_MAP_JSON must be a JSON object")
    return {str(k): str(v) for k, v in data.items()}


def subscription_product_map() -> dict[str, str]:
    """Return Apple subscription product_id → plan_id (canonical + legacy + env)."""
    mapping = dict(_CANONICAL_SUBSCRIPTION_PRODUCTS)
    mapping.update(_LEGACY_SUBSCRIPTION_ALIASES)
    mapping.update(_env_subscription_overrides())
    return mapping


def credit_product_map() -> dict[str, int]:
    """Return Apple credit consumable product_id → credit quantity."""
    return dict(_CREDIT_PRODUCTS)


def map_subscription_product(product_id: str) -> str:
    plan = subscription_product_map().get(product_id)
    if not plan:
        raise ValueError(f"Unknown Apple subscription product: {product_id}")
    return plan


def map_credit_product(product_id: str) -> int:
    credits = credit_product_map().get(product_id)
    if credits is None:
        raise ValueError(f"Unknown Apple credit product: {product_id}")
    return credits


def is_subscription_product(product_id: str) -> bool:
    return product_id in subscription_product_map()


def is_credit_product(product_id: str) -> bool:
    return product_id in credit_product_map()


def all_apple_product_ids() -> list[str]:
    """All known Apple product IDs (subscriptions + credits), sorted."""
    ids = set(subscription_product_map()) | set(credit_product_map())
    return sorted(ids)
