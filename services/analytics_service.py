# -*- coding: utf-8 -*-
"""
Analytics Service
Orchestrates analytics aggregation and optional real OpenAI usage costs.
Enriches new-client dashboard rows with Firestore profile + price hints.
"""

import asyncio
from typing import Any, Dict, List, Optional

from services.analytics_manager import analytics_manager
from services.openai_usage_service import openai_usage_service

_FIRESTORE_APP_ID = "linas-ai-bot-backend"

# Short hints for dashboard (full prices live in clinic materials / dynamic retrieval).
SERVICE_PRICE_HINTS = {
    "laser_hair_removal": "Varies by body area — see clinic price list",
    "tattoo_removal": "Varies by size & sessions — see clinic price list",
    "laser_tattoo_removal": "Varies by size & sessions — see clinic price list",
    "co2_laser": "Session-based — see clinic price list",
    "skin_whitening": "Varies by protocol — see clinic price list",
    "botox": "Per unit — see clinic price list",
    "fillers": "Per syringe — see clinic price list",
}


def _service_price_hint(service_key: str) -> str:
    if not service_key:
        return "—"
    k = str(service_key).strip().lower()
    return SERVICE_PRICE_HINTS.get(k, "See clinic price list — varies by case")


def _attach_service_pricing(row: Dict[str, Any]) -> None:
    services = row.get("services") or []
    row["services_pricing"] = [
        {"service": s, "price_hint": _service_price_hint(s)}
        for s in services
    ]


def _candidate_user_doc_ids(user_id: str) -> List[str]:
    from utils.utils import get_canonical_user_id_and_phone
    from utils.phone_utils import is_phone_like_user_id

    raw = str(user_id or "").strip()
    out: List[str] = []
    phone_guess = raw if is_phone_like_user_id(raw) else None
    canonical, _ = get_canonical_user_id_and_phone(raw, phone_guess)
    if canonical:
        out.append(canonical)
    if raw:
        out.append(raw)
    if raw.startswith("+") and len(raw) > 1:
        alt = raw[1:]
        if alt not in out:
            out.append(alt)
    elif raw and raw.isdigit() and not raw.startswith("+"):
        plus = f"+{raw}"
        if plus not in out:
            out.append(plus)
    seen = set()
    uniq = []
    for x in out:
        if x and x not in seen:
            seen.add(x)
            uniq.append(x)
    return uniq


def _read_firestore_user_profile(user_id: str) -> Optional[Dict[str, Any]]:
    from utils.utils import get_firestore_db

    db = get_firestore_db()
    if not db:
        return None
    users_root = db.collection("artifacts").document(_FIRESTORE_APP_ID).collection("users")
    for vid in _candidate_user_doc_ids(user_id):
        try:
            snap = users_root.document(vid).get()
            if snap.exists:
                d = snap.to_dict() or {}
                name = (d.get("name") or "").strip()
                phone_full = (d.get("phone_full") or "").strip()
                return {"name": name, "phone_full": phone_full or None}
        except Exception:
            continue
    return None


def _default_phone_display(user_id: str) -> str:
    from utils.phone_utils import is_phone_like_user_id, normalize_phone
    from utils.utils import get_canonical_user_id_and_phone

    raw = str(user_id or "").strip()
    if not raw:
        return ""
    if is_phone_like_user_id(raw):
        _, norm = get_canonical_user_id_and_phone(raw, raw)
        if norm:
            return norm if str(norm).startswith("+") else f"+{norm}"
        n = normalize_phone(raw)
        return n or raw
    return raw


def _live_chat_search_token(phone_display: str, user_id: str) -> str:
    """Query value for /live-chat?search= — prefer digits for phone-like ids."""
    from utils.phone_utils import is_phone_like_user_id
    import re

    raw = str(user_id or "").strip()
    if phone_display:
        digits = re.sub(r"\D", "", phone_display)
        if len(digits) >= 7:
            return digits
    if is_phone_like_user_id(raw):
        digits = re.sub(r"\D", "", raw)
        if len(digits) >= 7:
            return digits
        return raw
    return raw or phone_display or ""


def _is_real_name(name: str) -> bool:
    n = (name or "").strip()
    if not n:
        return False
    lower = n.lower()
    if lower in ("unknown", "unknown customer", "none", "null", "-"):
        return False
    return True


async def _enrich_new_client_row(row: Dict[str, Any]) -> None:
    uid = row.get("user_id")
    if not uid:
        return
    profile = await asyncio.to_thread(_read_firestore_user_profile, str(uid))
    phone_display = _default_phone_display(str(uid))
    name = ""
    if profile:
        name = profile.get("name") or ""
        if profile.get("phone_full"):
            phone_display = profile["phone_full"]
    row["customer_name"] = name
    row["has_name"] = _is_real_name(name)
    row["phone_display"] = phone_display
    row["live_chat_search"] = _live_chat_search_token(phone_display, str(uid))
    _attach_service_pricing(row)


async def _enrich_new_client_dashboard_rows(result: Dict[str, Any]) -> None:
    nc = result.get("new_clients")
    if not isinstance(nc, dict):
        return
    for key in ("booked_details", "asked_not_booked_details", "not_booked_details"):
        lst = nc.get(key)
        if not isinstance(lst, list):
            continue
        for row in lst:
            if isinstance(row, dict):
                await _enrich_new_client_row(row)


class AnalyticsService:
    """Service layer for analytics API consumers."""

    @staticmethod
    def _safe_days(value: Any, default: int = 7) -> int:
        try:
            return max(int(value), 1)
        except (TypeError, ValueError):
            return default

    async def get_analytics_summary(self, time_range: int = 7, use_real_costs: bool = True) -> Dict[str, Any]:
        safe_days = self._safe_days(time_range, default=7)
        result = analytics_manager.get_summary(days=safe_days)

        if not result.get("success"):
            return result

        token_usage = result.setdefault("token_usage", {})
        token_usage["source"] = "estimated"

        if use_real_costs:
            try:
                openai_usage = await openai_usage_service.get_usage_for_last_n_days(safe_days)
                if openai_usage.get("success"):
                    # Legacy GET /v1/usage often returns empty or 404 per day; we still get success=True
                    # with zeros and would overwrite good per-message estimates from analytics_events.jsonl.
                    # Only apply OpenAI billing totals when the API actually returned usage.
                    api_cost = float(openai_usage.get("total_cost_usd") or 0)
                    api_tokens = int(openai_usage.get("total_tokens") or 0)
                    if api_cost > 0 or api_tokens > 0:
                        token_usage["total_cost_usd"] = api_cost
                        token_usage["total_tokens"] = api_tokens
                        if safe_days > 0:
                            token_usage["avg_daily_tokens"] = api_tokens // safe_days
                            token_usage["avg_daily_cost_usd"] = round(api_cost / safe_days, 2)
                        token_usage["model_breakdown"] = openai_usage.get(
                            "model_breakdown", token_usage.get("model_breakdown", {})
                        )
                        token_usage["daily_costs"] = openai_usage.get("daily_costs", [])
                        token_usage["source"] = "openai_api"
                    else:
                        print(
                            "⚠️ AnalyticsService: OpenAI usage API returned no billable totals; "
                            "keeping event-based token_usage from analytics_events.jsonl"
                        )
            except Exception as e:
                print(f"⚠️ AnalyticsService: failed to fetch real OpenAI costs: {e}")

        try:
            await _enrich_new_client_dashboard_rows(result)
        except Exception as e:
            print(f"⚠️ AnalyticsService: new client row enrichment failed: {e}")

        return result


analytics_service = AnalyticsService()
