"""Platform-owner message economy: action costs, Copilot bands, IAP pack map.

Persisted in catalog_admin draft under ``economy`` so policy versions travel
with catalog revisions. Historical ledger rows keep the policy_version they
were charged under; changing this file does not rewrite history.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

POLICY_VERSION = "message-economy-v1"

DEFAULT_ACTION_COSTS: dict[str, Any] = {
    "ai_dm_reply": 1,
    "ai_public_comment": 1,
    "ai_comment_dm": 1,
    "ai_both_mode": "each",
    "followup_sent": 1,
}

DEFAULT_COPILOT: dict[str, Any] = {
    "confirm_threshold_messages": 2,
    "bands": [],
}


def _defaults() -> dict[str, Any]:
    return {
        "policy_version": POLICY_VERSION,
        "action_costs": dict(DEFAULT_ACTION_COSTS),
        "copilot": deepcopy(DEFAULT_COPILOT),
        "iap_message_quantities": {},
        "conversion_rate": None,
    }


def snapshot_economy(raw: Any) -> dict[str, Any]:
    base = _defaults()
    if not isinstance(raw, dict):
        return base
    costs = raw.get("action_costs") if isinstance(raw.get("action_costs"), dict) else {}
    copilot = raw.get("copilot") if isinstance(raw.get("copilot"), dict) else {}
    base["action_costs"].update({k: costs[k] for k in DEFAULT_ACTION_COSTS if k in costs})
    if "confirm_threshold_messages" in copilot:
        base["copilot"]["confirm_threshold_messages"] = int(copilot["confirm_threshold_messages"])
    if isinstance(copilot.get("bands"), list):
        base["copilot"]["bands"] = [dict(row) for row in copilot["bands"] if isinstance(row, dict)]
    if isinstance(raw.get("iap_message_quantities"), dict):
        base["iap_message_quantities"] = {
            str(k): int(v) for k, v in raw["iap_message_quantities"].items() if int(v) > 0
        }
    if raw.get("conversion_rate") is not None:
        try:
            base["conversion_rate"] = float(raw["conversion_rate"])
        except (TypeError, ValueError):
            base["conversion_rate"] = None
    base["policy_version"] = str(raw.get("policy_version") or POLICY_VERSION)
    return base


def load_economy() -> dict[str, Any]:
    from services.billing.membership.catalog_admin import peek_draft_economy

    return snapshot_economy(peek_draft_economy())


def validate_economy(raw: dict[str, Any]) -> dict[str, Any]:
    out = _defaults()
    costs = raw.get("action_costs") if isinstance(raw.get("action_costs"), dict) else {}
    for key in DEFAULT_ACTION_COSTS:
        if key == "ai_both_mode":
            mode = str(costs.get(key) or out["action_costs"][key]).strip().lower()
            if mode not in {"each", "once"}:
                raise ValueError("ai_both_mode must be each or once")
            out["action_costs"][key] = mode
            continue
        if key in costs:
            units = int(costs[key])
            if units < 0 or units > 100:
                raise ValueError(f"{key} must be 0..100")
            out["action_costs"][key] = units
    copilot = raw.get("copilot") if isinstance(raw.get("copilot"), dict) else {}
    if "confirm_threshold_messages" in copilot:
        threshold = int(copilot["confirm_threshold_messages"])
        if threshold < 1 or threshold > 10_000:
            raise ValueError("confirm_threshold_messages must be 1..10000")
        out["copilot"]["confirm_threshold_messages"] = threshold
    bands = copilot.get("bands") if isinstance(copilot.get("bands"), list) else []
    parsed: list[dict[str, Any]] = []
    last_max = -1.0
    for index, row in enumerate(bands):
        if not isinstance(row, dict) or row.get("enabled") is False:
            continue
        lo = float(row.get("min_usd") if row.get("min_usd") is not None else row.get("minimum_cost") or 0)
        hi_raw = row.get("max_usd") if row.get("max_usd") is not None else row.get("maximum_cost")
        hi = float(hi_raw) if hi_raw is not None else 10**9
        units = int(row.get("message_units") or row.get("messages") or 0)
        if lo < 0 or hi < lo or units < 1:
            raise ValueError(f"invalid copilot band at {index}")
        if lo < last_max:
            raise ValueError("copilot bands overlap")
        last_max = hi
        parsed.append({"min_usd": lo, "max_usd": hi, "message_units": units, "enabled": True})
    out["copilot"]["bands"] = parsed
    iap = raw.get("iap_message_quantities") if isinstance(raw.get("iap_message_quantities"), dict) else {}
    out["iap_message_quantities"] = {str(k).strip(): int(v) for k, v in iap.items() if str(k).strip() and int(v) > 0}
    if raw.get("conversion_rate") not in (None, ""):
        rate = float(raw["conversion_rate"])
        if rate <= 0:
            raise ValueError("conversion_rate must be > 0")
        out["conversion_rate"] = rate
    return out


def action_units(*, response_class: str, invocation_kind: str = "", comment_mode: str = "") -> int:
    from services.billing.membership.message_policy import ZERO_DEBIT

    if response_class in ZERO_DEBIT:
        return 0
    costs = load_economy()["action_costs"]
    kind = (invocation_kind or "").strip().lower()
    mode = (comment_mode or "").strip().lower()
    if kind == "followup" or response_class == "followup_sent":
        return int(costs["followup_sent"])
    if kind == "comment" or mode.startswith("ai_"):
        if mode == "ai_both":
            if costs["ai_both_mode"] == "once":
                return max(int(costs["ai_public_comment"]), int(costs["ai_comment_dm"]))
            return int(costs["ai_public_comment"]) + int(costs["ai_comment_dm"])
        if mode == "ai_comment":
            return int(costs["ai_public_comment"])
        if mode == "ai_dm":
            return int(costs["ai_comment_dm"])
        return int(costs["ai_public_comment"])
    return int(costs["ai_dm_reply"])


def copilot_units_for_cost(estimated_usd: float | None) -> int:
    economy = load_economy()
    bands = economy["copilot"]["bands"]
    if not bands or estimated_usd is None:
        return 1
    cost = max(0.0, float(estimated_usd))
    for band in bands:
        if band["min_usd"] <= cost <= band["max_usd"]:
            return int(band["message_units"])
    return int(bands[-1]["message_units"])


def copilot_requires_confirm(units: int) -> bool:
    threshold = int(load_economy()["copilot"]["confirm_threshold_messages"])
    return units >= threshold
