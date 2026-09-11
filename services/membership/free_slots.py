"""Free plan slot caps. Line budgets stay unenforced until the owner defines a line."""

from __future__ import annotations

from services.membership.message_catalog import require_message_plan
from services.membership.message_flags import free_enforcement_enabled


class SlotLimitError(PermissionError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _feature_plan_id(tenant_id: str) -> str:
    from services.entitlements_service import entitlements_store

    ent = entitlements_store.get(tenant_id)
    return str(ent.plan_id or "").strip().lower()


def slots_apply(tenant_id: str) -> bool:
    if not free_enforcement_enabled():
        return False
    return _feature_plan_id(tenant_id) in {"", "none", "free"}


def assert_can_add_service(tenant_id: str, current_count: int) -> None:
    if not slots_apply(tenant_id):
        return
    cap = int(require_message_plan("free").services_cap or 0)
    if current_count >= cap:
        raise SlotLimitError("FREE_SLOT_LIMIT", f"Free plans may keep {cap} services.")


def assert_can_add_product(tenant_id: str, current_count: int) -> None:
    if not slots_apply(tenant_id):
        return
    cap = int(require_message_plan("free").products_cap or 0)
    if current_count >= cap:
        raise SlotLimitError("FREE_SLOT_LIMIT", f"Free plans may keep {cap} products.")


def assert_can_add_branch(tenant_id: str, current_count: int) -> None:
    if not slots_apply(tenant_id):
        return
    cap = int(require_message_plan("free").branches_cap or 0)
    if current_count >= cap:
        raise SlotLimitError("FREE_SLOT_LIMIT", f"Free plans may keep {cap} branches.")


def _item_count(payload: object) -> int:
    if not isinstance(payload, dict):
        return 0
    items = payload.get("items")
    return len(items) if isinstance(items, list) else 0


def assert_cm_section_slots(
    tenant_id: str,
    section: str,
    payload: object,
    *,
    current_payload: object = None,
) -> None:
    """Reject Free growth past 5 services / 1 branch. Shrinking or in-place edits stay allowed."""
    if not slots_apply(tenant_id):
        return
    name = (section or "").strip().lower()
    if name not in {"services", "branches"}:
        return
    proposed = _item_count(payload)
    current = _item_count(current_payload)
    if proposed <= current:
        return
    if name == "services":
        assert_can_add_service(tenant_id, current)
        if proposed > int(require_message_plan("free").services_cap or 0):
            raise SlotLimitError("FREE_SLOT_LIMIT", "Free plans may keep 5 services.")
        return
    assert_can_add_branch(tenant_id, current)
    if proposed > int(require_message_plan("free").branches_cap or 0):
        raise SlotLimitError("FREE_SLOT_LIMIT", "Free plans may keep 1 branch.")
