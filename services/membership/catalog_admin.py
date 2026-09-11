"""Platform-admin draft overlays on the intended message catalog. Publish stays gated."""

from __future__ import annotations

import threading
from copy import deepcopy
from typing import Any

from services.membership.message_catalog import (
    PAID_PLANS,
    UNCONFIGURED_FREE_FIELDS,
    message_catalog_snapshot,
    offer_fields_for_plan,
)
from services.membership.units import MICRO_USD_PER_USD

_LOCK = threading.Lock()
_DRAFT: dict[str, Any] = {}
_REVISION = 1
_PUBLISHED = False
_AUDIT: list[dict[str, Any]] = []
_LOADED = False

_PLAN_OVERLAY_KEYS = ("intended_price_usd", "included_messages", "faq_capacity")


class CatalogPublishBlocked(Exception):
    def __init__(self, fields: list[str]) -> None:
        super().__init__("free_offer_unconfigured")
        self.fields = fields


def reset_catalog_admin_for_tests() -> None:
    with _LOCK:
        _DRAFT.clear()
        global _REVISION, _PUBLISHED, _LOADED
        _REVISION = 1
        _PUBLISHED = False
        _AUDIT.clear()
        _LOADED = True
    from services.membership.catalog_admin_store import reset_admin_state_for_tests

    reset_admin_state_for_tests()


def _apply_state(state: dict[str, Any] | None) -> None:
    global _REVISION, _PUBLISHED, _LOADED
    if state:
        _DRAFT.clear()
        _DRAFT.update(state.get("draft") or {})
        _REVISION = int(state.get("revision") or 1)
        _PUBLISHED = bool(state.get("published"))
        _AUDIT[:] = [row for row in (state.get("audit") or []) if isinstance(row, dict)]
    _LOADED = True


def _hydrate_unlocked() -> None:
    if _LOADED:
        return
    from services.membership.catalog_admin_store import load_admin_state

    _apply_state(load_admin_state())


def _refresh_unlocked() -> None:
    from services.membership.catalog_admin_store import load_admin_state, persist_enabled

    if not persist_enabled():
        _hydrate_unlocked()
        return
    _apply_state(load_admin_state())


def _persist_unlocked() -> None:
    from services.membership.catalog_admin_store import save_admin_state

    save_admin_state(draft=dict(_DRAFT), revision=_REVISION, published=_PUBLISHED, audit=list(_AUDIT))


def payment_readiness() -> dict[str, Any]:
    from services.membership.message_flags import message_billing_cutover

    return {
        "apple": {
            "status": "implemented",
            "sale_ready": False,
            "note": "Historical SKUs verify. Message-priced checkout waits for cutover.",
        },
        "google": {
            "status": "incomplete",
            "sale_ready": False,
            "blocker": "google_iap_not_fully_implemented",
        },
        "stripe": {
            "status": "legacy_token_packs",
            "sale_ready": False,
            "blocker": "not_message_subscription_checkout",
        },
        "annual_offers": {"status": "unconfigured", "sale_ready": False},
        "topup_packs": {"status": "unpriced", "sale_ready": False},
        "cutover": message_billing_cutover(),
    }


def _catalog_unlocked() -> dict[str, Any]:
    base = message_catalog_snapshot()
    if _DRAFT:
        base = _apply_draft(base, _DRAFT)
    base["admin_revision"] = _REVISION
    base["published"] = _PUBLISHED
    base["payment_readiness"] = payment_readiness()
    return base


def current_catalog() -> dict[str, Any]:
    with _LOCK:
        _refresh_unlocked()
        return _catalog_unlocked()


def _normalize_plan_overlay(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("plan overlay must be an object")
    out: dict[str, Any] = {}
    if "intended_price_usd" in raw:
        usd = float(raw["intended_price_usd"])
        if usd < 0:
            raise ValueError("intended_price_usd must be >= 0")
        out["intended_price_usd"] = usd
        out["intended_price_micro_usd"] = int(round(usd * MICRO_USD_PER_USD))
    if "included_messages" in raw:
        if raw["included_messages"] in (None, ""):
            raise ValueError("paid plans cannot clear included_messages")
        messages = int(raw["included_messages"])
        if messages < 0:
            raise ValueError("included_messages must be >= 0")
        out["included_messages"] = messages
    if "faq_capacity" in raw:
        faq = int(raw["faq_capacity"])
        if faq < 0:
            raise ValueError("faq_capacity must be >= 0")
        out["faq_capacity"] = faq
    return out


def _sanitize_plans(raw: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(raw, dict):
        raise ValueError("plans must be an object keyed by plan_id")
    out: dict[str, dict[str, Any]] = {}
    for plan_id, overlay in raw.items():
        pid = str(plan_id).strip().lower()
        if pid not in PAID_PLANS:
            raise ValueError(f"cannot draft unknown or free plan: {plan_id}")
        out[pid] = _normalize_plan_overlay(overlay)
    return out


def _sanitize_topup_overlays(raw: Any) -> dict[str, str]:
    items: list[Any]
    if isinstance(raw, dict):
        items = [
            {"pack_id": key, **(value if isinstance(value, dict) else {"product_id": value})}
            for key, value in raw.items()
        ]
    elif isinstance(raw, list):
        items = raw
    else:
        raise ValueError("topup_packs must be a list or object")
    out: dict[str, str] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        pack_id = str(item.get("pack_id") or "").strip()
        product_id = str(item.get("product_id") or "").strip()
        if pack_id and product_id:
            out[pack_id] = product_id
    return out


def _apply_draft(base: dict[str, Any], draft: dict[str, Any]) -> dict[str, Any]:
    out = deepcopy(base)
    if "ai_setup_daily_edit_limit" in draft:
        out["ai_setup_daily_edit_limit"] = int(draft["ai_setup_daily_edit_limit"])
    free = draft.get("free")
    if isinstance(free, dict):
        merged = dict(out.get("free") or {})
        merged.update(free)
        out["free"] = merged
        if free.get("included_messages") not in (None, ""):
            remaining = [
                field
                for field in UNCONFIGURED_FREE_FIELDS
                if field != "free_ai_message_allowance" and not (out["free"].get("configured") or {}).get(field)
            ]
            out["free"]["unconfigured_fields"] = remaining
    plans = draft.get("plans")
    if isinstance(plans, dict):
        rows = []
        for row in out.get("plans") or []:
            item = dict(row)
            overlay = plans.get(item.get("plan_id")) or {}
            if overlay:
                item.update(overlay)
                item["draft_overlay"] = True
                item["checkout_ready"] = False
            rows.append(item)
        out["plans"] = rows
    product_ids = draft.get("topup_packs")
    if isinstance(product_ids, dict):
        packs = []
        for pack in out.get("topup_packs") or []:
            row = dict(pack)
            mapped = product_ids.get(row.get("pack_id"))
            if mapped:
                row["product_id"] = mapped
            row["sale_ready"] = False
            if row.get("price_usd") in (None, ""):
                row["reason"] = "message_topup_prices"
            packs.append(row)
        out["topup_packs"] = packs
    return out


def update_draft(*, actor: str, changes: dict[str, Any], reason: str = "") -> dict[str, Any]:
    allowed: dict[str, Any] = {}
    if "ai_setup_daily_edit_limit" in changes:
        allowed["ai_setup_daily_edit_limit"] = changes["ai_setup_daily_edit_limit"]
    if "free" in changes:
        allowed["free"] = changes["free"]
    if "plans" in changes:
        allowed["plans"] = _sanitize_plans(changes["plans"])
    if "topup_packs" in changes:
        allowed["topup_packs"] = _sanitize_topup_overlays(changes["topup_packs"])
    with _LOCK:
        global _REVISION
        _refresh_unlocked()
        _DRAFT.update(allowed)
        _REVISION += 1
        _AUDIT.append({"actor": actor, "reason": reason, "revision": _REVISION, "fields": sorted(allowed)})
        _persist_unlocked()
        return _catalog_unlocked()


def publish(*, actor: str, reason: str = "") -> dict[str, Any]:
    catalog = current_catalog()
    free = catalog.get("free") or {}
    missing = list(free.get("unconfigured_fields") or UNCONFIGURED_FREE_FIELDS)
    if missing:
        raise CatalogPublishBlocked(missing)
    with _LOCK:
        global _PUBLISHED, _REVISION
        _PUBLISHED = True
        _REVISION += 1
        _AUDIT.append({"actor": actor, "reason": reason or "publish", "revision": _REVISION})
        _persist_unlocked()
        return _catalog_unlocked()


def published_offer_overlay(plan_id: str) -> dict[str, Any]:
    pid = (plan_id or "").strip().lower()
    with _LOCK:
        _refresh_unlocked()
        if not _PUBLISHED:
            return {}
        overlay = (_DRAFT.get("plans") or {}).get(pid) or {}
        return {key: overlay[key] for key in (*_PLAN_OVERLAY_KEYS, "intended_price_micro_usd") if key in overlay}


def effective_offer_fields(plan_id: str) -> dict[str, Any]:
    fields = offer_fields_for_plan(plan_id)
    overlay = published_offer_overlay(plan_id)
    if overlay:
        fields.update(overlay)
    return fields


def effective_included_messages(plan_id: str) -> int | None:
    value = effective_offer_fields(plan_id).get("included_messages")
    return None if value is None else int(value)


def published_sale_ready_pack(product_id: str) -> dict[str, Any] | None:
    pid = (product_id or "").strip()
    if not pid:
        return None
    catalog = current_catalog()
    if not catalog.get("published"):
        return None
    for pack in catalog.get("topup_packs") or []:
        if str(pack.get("product_id") or "") != pid:
            continue
        if not pack.get("sale_ready") or pack.get("price_usd") in (None, ""):
            return None
        if int(pack.get("quantity") or 0) <= 0:
            return None
        return dict(pack)
    return None


def audit_log() -> list[dict[str, Any]]:
    with _LOCK:
        return list(_AUDIT)
