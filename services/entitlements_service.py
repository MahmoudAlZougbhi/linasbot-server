"""Central entitlement service — backend is source of truth for plan access.

Purchase events may arrive from Apple, Google, or (optionally) Stripe.

Postgres SoT when LINAS_BILLING_BACKEND=postgres (default); file when explicitly set.

Subscription gate exemption (explicit allowlist only — not a hidden fallback):
  Env ``SUBSCRIPTION_EXEMPT_TENANT_IDS`` (comma-separated tenant ids).
  Default: ``linas`` — the reserved Linas Laser founder clinic tenant
  (``DEFAULT_TENANT_ID`` / ``LINASBOT_TENANT_ID``). Everyone else remains
  gated on an active/trial/grace paid plan. Set the env to a different
  comma-separated id list to replace the default; do not broaden the gate
  globally.
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from services.billing_backend import billing_uses_postgres, require_billing_pg_session
from services.plan_economics import PLAN_FEATURES, PLAN_PRICES_USD, recommend_allowance
from storage.persistent_storage import _DATA_ROOT as _DEFAULT_DATA_ROOT

# Overridable in tests
_DATA_ROOT = _DEFAULT_DATA_ROOT

# Linas Laser founder clinic — reserved tenant_id (see services/cm/constants.DEFAULT_TENANT_ID).
DEFAULT_SUBSCRIPTION_EXEMPT_TENANTS = frozenset({"linas"})


def subscription_exempt_tenant_ids() -> frozenset[str]:
    """Explicit tenant ids that receive app_access without a paid plan."""
    raw = (os.getenv("SUBSCRIPTION_EXEMPT_TENANT_IDS") or "linas").strip()
    ids = {part.strip().lower() for part in raw.split(",") if part.strip()}
    return frozenset(ids or DEFAULT_SUBSCRIPTION_EXEMPT_TENANTS)


def is_subscription_exempt_tenant(tenant_id: str | None) -> bool:
    tid = (tenant_id or "").strip().lower()
    if not tid:
        return False
    return tid in subscription_exempt_tenant_ids()


EntitlementStatus = Literal[
    "none",
    "active",
    "trial",
    "grace",
    "canceled",
    "expired",
    "refunded",
    "revoked",
]


@dataclass
class TenantEntitlement:
    tenant_id: str
    plan_id: str
    status: EntitlementStatus
    source: str  # apple | google | stripe | admin | none
    current_period_end: float | None
    included_credits: int
    extra_credits: int
    features: dict[str, bool]
    updated_at: float
    store_original_transaction_id: str | None = None


class EntitlementsStore:
    def __init__(self, root: Path | None = None) -> None:
        self._lock = threading.RLock()
        self._root = root or (Path(_DATA_ROOT) / "entitlements")
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, tenant_id: str) -> Path:
        return self._root / f"{tenant_id}.json"

    def _empty(self, tenant_id: str) -> TenantEntitlement:
        return TenantEntitlement(
            tenant_id=tenant_id,
            plan_id="none",
            status="none",
            source="none",
            current_period_end=None,
            included_credits=0,
            extra_credits=0,
            features={},
            updated_at=time.time(),
        )

    def get(self, tenant_id: str) -> TenantEntitlement:
        if billing_uses_postgres():
            from services.entitlements_pg_store import get_entitlement

            with require_billing_pg_session() as session:
                data = get_entitlement(session, tenant_id)
            if data is None:
                return self._empty(tenant_id)
            return TenantEntitlement(**data)
        path = self._path(tenant_id)
        with self._lock:
            if not path.is_file():
                return self._empty(tenant_id)
            data = json.loads(path.read_text(encoding="utf-8"))
        return TenantEntitlement(**data)

    def save(self, ent: TenantEntitlement) -> TenantEntitlement:
        ent.updated_at = time.time()
        if billing_uses_postgres():
            from services.entitlements_pg_store import save_entitlement

            with require_billing_pg_session() as session:
                save_entitlement(session, asdict(ent))
            return ent
        with self._lock:
            self._path(ent.tenant_id).write_text(json.dumps(asdict(ent)), encoding="utf-8")
        return ent

    def set_plan(
        self,
        *,
        tenant_id: str,
        plan_id: str,
        status: EntitlementStatus,
        source: str,
        store_original_transaction_id: str | None = None,
        period_days: int = 30,
    ) -> TenantEntitlement:
        if plan_id not in PLAN_PRICES_USD and plan_id != "none":
            raise ValueError(f"Unknown plan: {plan_id}")
        allowance = recommend_allowance(plan_id) if plan_id in PLAN_PRICES_USD else None
        existing = self.get(tenant_id)
        ent = TenantEntitlement(
            tenant_id=tenant_id,
            plan_id=plan_id,
            status=status,
            source=source,
            current_period_end=time.time() + period_days * 86400 if status in {"active", "trial", "grace"} else None,
            included_credits=allowance.included_credits if allowance else 0,
            extra_credits=existing.extra_credits,
            features=dict(PLAN_FEATURES.get(plan_id, {})),
            updated_at=time.time(),
            store_original_transaction_id=store_original_transaction_id,
        )
        return self.save(ent)


entitlements_store = EntitlementsStore()


def tenant_has_app_access(tenant_id: str) -> bool:
    """True when the tenant may use the authenticated app (active/trial/grace).

    Explicit subscription-exempt tenants (``SUBSCRIPTION_EXEMPT_TENANT_IDS``,
    default ``linas`` / Linas Laser) also receive app_access without a plan.
    """
    if is_subscription_exempt_tenant(tenant_id):
        return True
    ent = entitlements_store.get(tenant_id)
    return ent.status in {"active", "trial", "grace"} and ent.plan_id not in {"", "none"}


def get_tenant_entitlement_public(tenant_id: str) -> dict[str, Any]:
    ent = entitlements_store.get(tenant_id)
    price = PLAN_PRICES_USD.get(ent.plan_id)
    from services.plan_economics import PLAN_ADDITIONAL_SEATS, PLAN_FAQ_MAX_ENTRIES

    # Compute gate fields first — FAQ enrichment must never 500 /api/entitlements/me
    # (mobile fail-closes the subscription gate on any entitlements error).
    exempt = is_subscription_exempt_tenant(tenant_id)
    app_access = tenant_has_app_access(tenant_id)
    # Catalog features are SoT for known plan_ids; do not trust stale stored blobs.
    features = dict(PLAN_FEATURES.get(ent.plan_id) or ent.features or {})
    faq: dict[str, Any]
    try:
        from services.faq_entitlements import get_faq_entitlement

        faq = get_faq_entitlement(tenant_id)
    except Exception:
        faq = {
            "faq_enabled": False,
            "faq_max_entries": PLAN_FAQ_MAX_ENTRIES.get(ent.plan_id, 0),
            "faq_used_entries": 0,
            "quota_display": "0 / 0",
        }
    features.setdefault("faq_enabled", bool(faq.get("faq_enabled")))
    display_name = None
    additional_seats = PLAN_ADDITIONAL_SEATS.get(ent.plan_id)
    comment_automation = bool(features.get("comment_automation"))
    if ent.plan_id in PLAN_PRICES_USD:
        from services.membership.plan_catalog import require_plan

        display_name = require_plan(ent.plan_id).display_name
    return {
        "tenant_id": ent.tenant_id,
        "plan_id": ent.plan_id,
        "display_name": display_name,
        "status": ent.status,
        "source": ent.source,
        "price_usd": price,
        "current_period_end": ent.current_period_end,
        "included_credits": ent.included_credits,
        "extra_credits": ent.extra_credits,
        "purchased_credits": ent.extra_credits,
        "additional_seats": additional_seats,
        "additional_seats_unlimited": additional_seats is None if ent.plan_id in PLAN_PRICES_USD else False,
        "comment_automation": comment_automation,
        "features": features,
        "faq_enabled": faq.get("faq_enabled"),
        "faq_max_entries": faq.get("faq_max_entries", PLAN_FAQ_MAX_ENTRIES.get(ent.plan_id, 0)),
        "faq_used_entries": faq.get("faq_used_entries"),
        "faq_quota_display": faq.get("quota_display"),
        "updated_at": ent.updated_at,
        "app_access": app_access,
        "subscription_required": not exempt,
        "subscription_exempt": exempt,
        "iap_purchase_in_app": False,
        # Omit iap_note entirely — JSON null previously broke mobile Zod
        # (z.string().optional rejects null) and fail-closed the subscription gate.
    }


def assert_feature(tenant_id: str, feature: str) -> None:
    ent = entitlements_store.get(tenant_id)
    if ent.status not in {"active", "trial", "grace"}:
        raise PermissionError("Active subscription required")
    features = PLAN_FEATURES.get(ent.plan_id) or ent.features or {}
    if not features.get(feature):
        raise PermissionError(f"Plan does not include feature: {feature}")


def apply_store_notification(
    *,
    tenant_id: str,
    plan_id: str,
    status: EntitlementStatus,
    source: str,
    original_transaction_id: str,
    idempotency_key: str,
) -> dict[str, Any]:
    """Idempotent entitlement update from Apple/Google server notifications."""
    if billing_uses_postgres():
        from services.entitlements_pg_store import mark_processed_event, processed_event_exists

        with require_billing_pg_session() as session:
            if processed_event_exists(session, idempotency_key):
                return {"duplicate": True, "entitlement": get_tenant_entitlement_public(tenant_id)}
        ent = entitlements_store.set_plan(
            tenant_id=tenant_id,
            plan_id=plan_id,
            status=status,
            source=source,
            store_original_transaction_id=original_transaction_id,
        )
        with require_billing_pg_session() as session:
            if not mark_processed_event(
                session,
                idempotency_key=idempotency_key,
                tenant_id=tenant_id,
                meta={"event_id": idempotency_key, "uuid": uuid.uuid4().hex},
            ):
                return {"duplicate": True, "entitlement": get_tenant_entitlement_public(tenant_id)}
        return {"duplicate": False, "entitlement": asdict(ent)}

    processed_dir = Path(_DATA_ROOT) / "entitlements" / "processed_events"
    processed_dir.mkdir(parents=True, exist_ok=True)
    marker = processed_dir / f"{idempotency_key}.json"
    if marker.is_file():
        return {"duplicate": True, "entitlement": get_tenant_entitlement_public(tenant_id)}
    ent = entitlements_store.set_plan(
        tenant_id=tenant_id,
        plan_id=plan_id,
        status=status,
        source=source,
        store_original_transaction_id=original_transaction_id,
    )
    marker.write_text(
        json.dumps(
            {
                "tenant_id": tenant_id,
                "event_id": idempotency_key,
                "ts": time.time(),
                "uuid": uuid.uuid4().hex,
            }
        ),
        encoding="utf-8",
    )
    return {"duplicate": False, "entitlement": asdict(ent)}
