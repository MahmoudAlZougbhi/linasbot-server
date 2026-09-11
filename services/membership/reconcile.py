"""Read-only ledger checks. Never invents grants or converts credits."""

from __future__ import annotations

from typing import Any

from services.membership.lot_window import lot_is_live
from services.membership.message_ledger import snapshot
from services.membership.pg_store import store_backend


def ledger_health(tenant_id: str) -> dict[str, Any]:
    snap = snapshot(tenant_id)
    negative = [lot.lot_id for lot in snap.lots if lot.remaining < 0 or lot.granted < 0]
    live_remaining = sum(lot.remaining for lot in snap.lots if lot_is_live(lot))
    balanced = snap.remaining == max(0, live_remaining - snap.reserved)
    return {
        "tenant_id": snap.tenant_id,
        "ok": not negative and balanced and snap.remaining >= 0,
        "negative_lots": negative,
        "balanced": balanced,
        "included": snap.included,
        "purchased": snap.purchased,
        "reserved": snap.reserved,
        "remaining": snap.remaining,
        "store": store_backend(),
        "stale_included": [
            lot.lot_id for lot in snap.lots if lot.kind == "included" and lot.expires and not lot_is_live(lot)
        ],
    }
