"""Legacy GPT chat-response helpers group 8."""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

import config
from services import api_integrations
from services.booking.resolver import match_best_body_part_row, server_may_infer_body_parts
from services.chat_response_service_constants import (
    HAIR_REMOVAL_MACHINE_IDS,
    LASER_HAIR_REMOVAL_SERVICE_IDS,
    _safe_int,
)


async def _resolve_body_part_ids_from_area_hint(
    area_hint: str, service_id: int, machine_id: int | None = None
) -> list[int] | None:
    """Resolve body_part_ids when only a human-readable area (e.g. back) is known."""
    if not server_may_infer_body_parts():
        return None
    if not area_hint or not str(area_hint).strip():
        return None
    static_ids = _area_name_to_body_part_ids(area_hint, service_id)
    if static_ids:
        return static_ids
    al = area_hint.strip().lower()
    al_compact = re.sub(r"[\s_\-]+", "", al)
    needle_terms = ("back", "ظهر", "ضهر", "dahr", "dahre", "عمود فقري")
    hand_terms = ("hand", "hands", "eideh", "eide", "يد", "اليد", "معصم", "wrist", "forearm", "arm")
    try:
        bp_resp = await api_integrations.get_body_parts(service_id=service_id, machine_id=machine_id)
        if not bp_resp.get("success") or not isinstance(bp_resp.get("data"), list):
            return None
        underarm_hint = (
            "underarm" in al_compact
            or "armpit" in al
            or "aisselle" in al
            or "axilla" in al
            or "ابط" in area_hint
            or "إبط" in area_hint
        )
        if underarm_hint:
            for item in bp_resp["data"]:
                name = (item.get("name") or item.get("body_part") or item.get("title") or "").strip().lower()
                if not name:
                    continue
                if any(u in name for u in ("underarm", "armpit", "ابط", "إبط", "aisselle", "axilla")):
                    bid = _safe_int(item.get("id"))
                    if bid is not None and bid > 0:
                        return [bid]
        if al in hand_terms or any(t in al for t in ("eideh", "eide", "hand", "hands", "wrist", "معصم", "forearm")):
            for item in bp_resp["data"]:
                name = (item.get("name") or item.get("body_part") or item.get("title") or "").strip().lower()
                if not name:
                    continue
                if any(h in name for h in ("hand", "يد", "معصم", "wrist", "forearm", "arm", "ذراع")):
                    bid = _safe_int(item.get("id"))
                    if bid is not None:
                        return [bid]
        for item in bp_resp["data"]:
            name = (item.get("name") or item.get("body_part") or item.get("title") or "").strip().lower()
            if not name:
                continue
            if any(term in name for term in needle_terms):
                bid = _safe_int(item.get("id"))
                return [bid] if bid is not None else None
        bid = match_best_body_part_row(bp_resp["data"], area_hint)
        if bid is not None:
            return [bid]
    except Exception as ex:
        print(f"_resolve_body_part_ids_from_area_hint: {ex}")
    return None


def _user_explicitly_requests_machine_change(text: str | None) -> bool:
    s = (text or "").strip().lower()
    if not s:
        return False
    return any(
        token in s
        for token in (
            "machine",
            "device",
            "جهاز",
            "الماكينة",
            "المكنة",
            "neo",
            "candela",
            "quadro",
            "نيو",
            "كانديلا",
            "كوادرو",
        )
    )


async def _resolve_machine_for_booking(
    service_id: int | None,
    candidate: int | None,
    preferred_existing_machine_id: int | None = None,
) -> int | None:
    """
    Only laser hair removal (1, 12) uses the customer's machine choice from get_machines.
    Tattoo, CO2, whitening, etc. have a fixed device on the backend — ignore wrong GPT picks
    and map by machine name from the API list.
    """
    sid = _safe_int(service_id)
    cand = _safe_int(candidate)
    preferred_existing = _safe_int(preferred_existing_machine_id)
    fallback = _safe_int(getattr(config, "DEFAULT_MACHINE_ID", None))
    if fallback is None:
        fallback = 1

    def _first_non_none(*values: int | None) -> int | None:
        for value in values:
            if value is not None:
                return value
        return None

    if sid in LASER_HAIR_REMOVAL_SERVICE_IDS:
        try:
            resp = await api_integrations.get_machines()
            if resp.get("success") and isinstance(resp.get("data"), list):
                hair_ids: list[int] = []
                for machine in resp["data"]:
                    mid = _safe_int(machine.get("id"))
                    name = str(machine.get("name") or "").strip().lower()
                    if mid is None:
                        continue
                    if mid in HAIR_REMOVAL_MACHINE_IDS or any(kw in name for kw in ("neo", "candela", "quadro")):
                        hair_ids.append(mid)
                hair_allowed = set(hair_ids)
                if cand is not None and cand not in hair_allowed:
                    return None
                for choice in (cand, preferred_existing, fallback):
                    if choice is not None and choice in hair_allowed:
                        return choice
                if hair_ids:
                    return hair_ids[0]
        except Exception as ex:
            print(f"_resolve_machine_for_booking: {ex}")
        for choice in (cand, preferred_existing, fallback):
            if choice is not None and choice in HAIR_REMOVAL_MACHINE_IDS:
                return choice
        return _first_non_none(preferred_existing, cand, fallback)
    try:
        resp = await api_integrations.get_machines()
        if not resp.get("success") or not isinstance(resp.get("data"), list):
            return _first_non_none(cand, preferred_existing, fallback)
        machines = resp["data"]
        allowed_ids = {_safe_int(m.get("id")) for m in machines}
        allowed_ids.discard(None)

        def nm(m: dict) -> str:
            return (m.get("name") or "").strip().lower()

        def first_id(pred: Any) -> int | None:
            for m in machines:
                if pred(nm(m)):
                    mid = _safe_int(m.get("id"))
                    if mid is not None:
                        return mid
            return None

        if cand is not None and cand in allowed_ids:
            return cand
        if preferred_existing is not None and preferred_existing in allowed_ids:
            return preferred_existing

        if sid == 13:
            mid = first_id(lambda n: "pico" in n)
            if mid is not None:
                return mid
            mid = first_id(lambda n: "tattoo" in n or "وشم" in n)
            if mid is not None:
                return mid
        if sid in (2, 11):
            mid = first_id(lambda n: "co2" in n)
            if mid is not None:
                return mid
        if sid in (4, 5, 14):
            mid = first_id(lambda n: "dpl" in n)
            if mid is not None:
                return mid
    except Exception as ex:
        print(f"_resolve_machine_for_booking: {ex}")
    return _first_non_none(preferred_existing, cand, fallback)


def _area_name_to_body_part_ids(area_name: str, service_id: int) -> list[int] | None:
    """
    Map area name (e.g. full body, full kel shi) to body_part_ids. Uses app_settings mapping
    first, then common full-body detection. Returns None if no mapping found.
    """
    if not area_name or not str(area_name).strip():
        return None
    area_lower = str(area_name).strip().lower()
    mapping = _get_area_to_body_part_mapping()
    # Check explicit mapping first
    for key in ["full_body", "full body", "full", "full_body_laser"]:
        if key in mapping:
            ids = mapping[key]
            if isinstance(ids, list) and ids:
                return [int(x) for x in ids if _safe_int(x) is not None]
    # Full body variants - use mapping if available
    full_body_keys = ["full body", "full kel shi", "full kel chi", "جسم كامل", "كامل", "full", "full body laser"]
    if any(k in area_lower or area_lower == k for k in full_body_keys):
        return mapping.get("full_body") or mapping.get("full")
    return mapping.get(area_lower)


def _get_area_to_body_part_mapping() -> dict[Any, Any]:
    """Load area->body_part_ids mapping from app_settings or use defaults."""
    try:
        from storage.persistent_storage import APP_SETTINGS_FILE

        with open(APP_SETTINGS_FILE, encoding="utf-8") as f:
            settings = json.load(f)
        m = settings.get("booking", {}).get("areaToBodyPartIds", {})
        if isinstance(m, dict) and m:
            return m
    except Exception:
        pass
    return {}


async def _fetch_customer_file_summary_for_ai(customer_phone_clean: str) -> str | None:
    """
    Fetch full customer file summary for AI context: services, sessions (done + available only),
    body parts per service, payment, dates, machines. Excludes postponed sessions.
    Returns formatted summary string or None if customer not found / API error.
    """
    if not customer_phone_clean or not str(customer_phone_clean).strip():
        return None
    try:
        cust_resp = await api_integrations.get_customer_by_phone(phone=customer_phone_clean)
        if not cust_resp.get("success") or not cust_resp.get("data"):
            return None
        data = cust_resp["data"]
        customer_id = data.get("id")
        if customer_id is None:
            return None

        # Fetch sessions and payment in parallel (faster)
        sessions_resp, payment_resp = await asyncio.gather(
            api_integrations.get_customer_sessions(customer_id=customer_id),
            api_integrations.check_appointment_payment(phone=customer_phone_clean),
        )

        lines = ["**📁 CUSTOMER FILE SUMMARY (use this when answering about their treatments):**"]

        # Sessions: only done + available (exclude postponed, paused)
        INCLUDE_STATUSES = {"done", "available"}
        sessions_raw = []
        if sessions_resp.get("success") and sessions_resp.get("data"):
            sess_data = sessions_resp["data"]
            if isinstance(sess_data, list):
                sessions_raw = sess_data
            elif isinstance(sess_data, dict) and "sessions" in sess_data:
                sessions_raw = sess_data.get("sessions", [])
            elif isinstance(sess_data, dict) and "data" in sess_data:
                sessions_raw = sess_data.get("data", [])

        sessions_included = []
        for s in sessions_raw:
            status = (s.get("status") or "").strip().lower()
            if status in INCLUDE_STATUSES:
                sessions_included.append(s)

        if sessions_included:
            # Group by service
            by_service: dict[str, list[dict]] = {}
            for s in sessions_included:
                svc = (s.get("service") or s.get("service_name") or "Unknown").strip()
                if svc not in by_service:
                    by_service[svc] = []
                by_service[svc].append(s)

            for svc_name, svc_sessions in by_service.items():
                lines.append(f"\n- **Service**: {svc_name} ({len(svc_sessions)} sessions)")
                body_parts = set()
                for s in svc_sessions:
                    bp = s.get("body_part") or s.get("body_area") or s.get("area")
                    if bp:
                        body_parts.add(str(bp).strip())
                if body_parts:
                    lines.append(f"  - Body parts: {', '.join(sorted(body_parts))}")
                for s in svc_sessions:
                    date_str = s.get("date") or s.get("appointment_date") or ""
                    machine = s.get("machine") or s.get("machine_name") or ""
                    sess_num = s.get("session_number")
                    status = s.get("status", "")
                    parts = [f"  - {status}"]
                    if date_str:
                        parts.append(f"date: {date_str}")
                    if machine:
                        parts.append(f"machine: {machine}")
                    if sess_num is not None:
                        parts.append(f"session #{sess_num}")
                    lines.append(" ".join(parts))
        else:
            lines.append("\n- No sessions (done or available) found.")

        # Payment
        if payment_resp.get("success") and payment_resp.get("data"):
            pay = payment_resp["data"]
            amount = pay.get("amount") or pay.get("paid") or pay.get("total_paid")
            if amount is not None:
                lines.append(f"\n- **Payment**: {amount}")
            status_pay = pay.get("status") or pay.get("payment_status")
            if status_pay:
                lines.append(f"- **Payment status**: {status_pay}")

        return "\n".join(lines) if len(lines) > 1 else None
    except Exception as e:
        print(
            f"⚠️ _fetch_customer_file_summary_for_ai failed for ***{str(customer_phone_clean)[-4:] if customer_phone_clean else ''}: {e}"
        )
        return None
