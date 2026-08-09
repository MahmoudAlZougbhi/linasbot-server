"""Central entitlement service — backend is source of truth for plan access.

Purchase events may arrive from Apple, Google, or (optionally) Stripe.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from services.plan_economics import PLAN_FEATURES, PLAN_PRICES_USD, recommend_allowance
from storage.persistent_storage import _DATA_ROOT as _DEFAULT_DATA_ROOT

# Overridable in tests
_DATA_ROOT = _DEFAULT_DATA_ROOT

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

    def get(self, tenant_id: str) -> TenantEntitlement:
        path = self._path(tenant_id)
        with self._lock:
            if not path.is_file():
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
            data = json.loads(path.read_text(encoding="utf-8"))
        return TenantEntitlement(**data)

    def save(self, ent: TenantEntitlement) -> TenantEntitlement:
        ent.updated_at = time.time()
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


def get_tenant_entitlement_public(tenant_id: str) -> dict[str, Any]:
    ent = entitlements_store.get(tenant_id)
    price = PLAN_PRICES_USD.get(ent.plan_id)
    return {
        "tenant_id": ent.tenant_id,
        "plan_id": ent.plan_id,
        "status": ent.status,
        "source": ent.source,
        "price_usd": price,
        "current_period_end": ent.current_period_end,
        "included_credits": ent.included_credits,
        "extra_credits": ent.extra_credits,
        "features": ent.features,
        "updated_at": ent.updated_at,
    }


def assert_feature(tenant_id: str, feature: str) -> None:
    ent = entitlements_store.get(tenant_id)
    if ent.status not in {"active", "trial", "grace"}:
        raise PermissionError("Active subscription required")
    if not ent.features.get(feature):
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
        json.dumps({"tenant_id": tenant_id, "event_id": idempotency_key, "ts": time.time(), "uuid": uuid.uuid4().hex}),
        encoding="utf-8",
    )
    return {"duplicate": False, "entitlement": asdict(ent)}
