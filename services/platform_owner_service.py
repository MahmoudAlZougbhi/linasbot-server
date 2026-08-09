"""Platform owner control center metrics and audited admin actions."""

from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from services.entitlements_service import entitlements_store
from services.plan_economics import PLAN_PRICES_USD
from storage.persistent_storage import _DATA_ROOT


@dataclass
class AdminAction:
    id: str
    actor_user_id: str
    action: str
    tenant_id: str
    details: dict[str, Any]
    created_at: float


class PlatformOwnerService:
    def __init__(self, root: Path | None = None) -> None:
        self._lock = threading.RLock()
        self._root = root or (Path(_DATA_ROOT) / "platform_owner")
        self._root.mkdir(parents=True, exist_ok=True)
        self._suspended: set[str] = set()
        self._load_suspended()

    def _suspended_path(self) -> Path:
        return self._root / "suspended_tenants.json"

    def _actions_path(self) -> Path:
        return self._root / "admin_actions.jsonl"

    def _load_suspended(self) -> None:
        path = self._suspended_path()
        if path.is_file():
            try:
                self._suspended = set(json.loads(path.read_text(encoding="utf-8")))
            except Exception:
                self._suspended = set()

    def log_action(self, *, actor_user_id: str, action: str, tenant_id: str, details: dict[str, Any]) -> AdminAction:
        entry = AdminAction(
            id=uuid.uuid4().hex,
            actor_user_id=actor_user_id,
            action=action,
            tenant_id=tenant_id,
            details=details,
            created_at=time.time(),
        )
        with self._lock:
            with self._actions_path().open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(asdict(entry)) + "\n")
        return entry

    def suspend_tenant(self, *, actor_user_id: str, tenant_id: str, reason: str) -> None:
        self._suspended.add(tenant_id)
        self._suspended_path().write_text(json.dumps(sorted(self._suspended)), encoding="utf-8")
        self.log_action(
            actor_user_id=actor_user_id,
            action="suspend",
            tenant_id=tenant_id,
            details={"reason": reason},
        )

    def reactivate_tenant(self, *, actor_user_id: str, tenant_id: str) -> None:
        self._suspended.discard(tenant_id)
        self._suspended_path().write_text(json.dumps(sorted(self._suspended)), encoding="utf-8")
        self.log_action(
            actor_user_id=actor_user_id,
            action="reactivate",
            tenant_id=tenant_id,
            details={},
        )

    def is_suspended(self, tenant_id: str) -> bool:
        return tenant_id in self._suspended

    def business_metrics(self) -> dict[str, Any]:
        root = Path(_DATA_ROOT) / "entitlements"
        tenants: list[dict[str, Any]] = []
        if root.is_dir():
            for path in root.glob("*.json"):
                try:
                    tenants.append(json.loads(path.read_text(encoding="utf-8")))
                except Exception:
                    continue
        active = [t for t in tenants if t.get("status") in {"active", "trial", "grace"}]
        plan_mix: dict[str, int] = {}
        mrr = 0.0
        for t in active:
            plan = str(t.get("plan_id") or "none")
            plan_mix[plan] = plan_mix.get(plan, 0) + 1
            mrr += float(PLAN_PRICES_USD.get(plan, 0.0))
        faq_analytics: dict[str, Any] = {}
        try:
            from services.faq_metrics import platform_owner_faq_analytics

            faq_analytics = platform_owner_faq_analytics()
        except Exception:
            faq_analytics = {"tenants": [], "totals": {}}
        return {
            "total_tenants_with_entitlement_file": len(tenants),
            "active_subscriptions": len(active),
            "canceled": len([t for t in tenants if t.get("status") == "canceled"]),
            "mrr_usd": round(mrr, 2),
            "arr_estimate_usd": round(mrr * 12, 2),
            "plan_mix": plan_mix,
            "suspended_tenants": sorted(self._suspended),
            "faq_smart_answers": faq_analytics,
        }

    def tenant_detail(self, tenant_id: str) -> dict[str, Any]:
        from services.credit_ledger_service import credit_ledger_service
        from services.integration_capabilities import list_tenant_integration_status

        ent = entitlements_store.get(tenant_id)
        return {
            "tenant_id": tenant_id,
            "suspended": self.is_suspended(tenant_id),
            "entitlement": {
                "plan_id": ent.plan_id,
                "status": ent.status,
                "included_credits": ent.included_credits,
                "extra_credits": ent.extra_credits,
                "features": ent.features,
            },
            "credit_balance": credit_ledger_service.get_balance(tenant_id),
            "integrations": list_tenant_integration_status(tenant_id),
            "estimated_revenue_usd": PLAN_PRICES_USD.get(ent.plan_id, 0.0),
        }


platform_owner_service = PlatformOwnerService()
