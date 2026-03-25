"""
Resolve Smart Messaging *test* template placeholders from live CRM data (same phone as recipient).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import config
from services.api_integrations import (
    check_next_appointment,
    get_customer_by_phone,
    get_customer_appointments,
)
from utils.phone_utils import normalize_phone

_EXCLUDED = frozenset(
    {"done", "completed", "cancelled", "canceled", "missed", "no_show", "noshow"}
)


def _apt_status_lower(row: dict) -> str:
    return str(row.get("status") or "").strip().lower()


def _row_ok(row: dict) -> bool:
    return _apt_status_lower(row) not in _EXCLUDED


def _is_blank_scalar(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, (dict, list)):
        return False
    return not str(v).strip()


def _coalesce_appointment_row(row: dict) -> dict:
    """
    BOC often nests fields under appointment_details. Merge base + nested (nested overwrites),
    then restore non-blank base values where nested overwrote with empty strings (common bug).
    """
    if not isinstance(row, dict):
        return {}
    nested = row.get("appointment_details")
    base = {k: v for k, v in row.items() if k != "appointment_details"}
    if not isinstance(nested, dict):
        return base
    merged = {**base, **nested}
    for k, vb in base.items():
        if _is_blank_scalar(merged.get(k)) and not _is_blank_scalar(vb):
            merged[k] = vb
    return merged


def _extract_customer_appointments_list(response_payload: dict) -> List[dict]:
    if not isinstance(response_payload, dict):
        return []
    data = response_payload.get("data")
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        if isinstance(data.get("appointments"), list):
            return [item for item in data.get("appointments", []) if isinstance(item, dict)]
        if isinstance(data.get("data"), list):
            return [item for item in data.get("data", []) if isinstance(item, dict)]
        appointment_payload = data.get("appointment")
        if isinstance(appointment_payload, dict):
            return [appointment_payload]
        for key in ("appointment_id", "id", "appointmentId"):
            if data.get(key) is not None:
                return [data]
    return []


def _extract_next_appointment_dict(response_payload: dict) -> dict:
    if not isinstance(response_payload, dict) or not response_payload.get("success"):
        return {}
    data = response_payload.get("data")
    if isinstance(data, dict):
        ap = data.get("appointment")
        if isinstance(ap, dict):
            return ap
        if any(data.get(k) is not None for k in ("appointment_id", "id", "appointmentId", "date")):
            return data
    return {}


def _customer_name_from_crm(data: Any) -> str:
    if not isinstance(data, dict):
        return ""
    for key in ("name", "customer_name", "full_name", "display_name"):
        v = data.get(key)
        if v and str(v).strip():
            return str(v).strip()
    cust = data.get("customer")
    if isinstance(cust, dict):
        for key in ("name", "customer_name", "full_name"):
            v = cust.get(key)
            if v and str(v).strip():
                return str(v).strip()
    return ""


def _service_label(row: dict) -> str:
    if not isinstance(row, dict):
        return ""
    svc = (
        row.get("service")
        or row.get("service_name")
        or row.get("service_title")
        or row.get("treatment_name")
    )
    if isinstance(svc, dict):
        s = str(svc.get("name") or svc.get("title") or "").strip()
        if s:
            return s
    elif svc and str(svc).strip():
        return str(svc).strip()
    nested = row.get("appointment_details")
    if isinstance(nested, dict):
        inner = {k: v for k, v in nested.items() if k != "appointment_details"}
        return _service_label(inner)
    return ""


def _branch_label(row: dict) -> str:
    if not isinstance(row, dict):
        return ""
    br = (
        row.get("branch")
        or row.get("branch_name")
        or row.get("branch_title")
        or row.get("location")
        or row.get("location_name")
        or row.get("clinic_name")
    )
    if isinstance(br, dict):
        s = str(br.get("name") or br.get("title") or "").strip()
        if s:
            return s
    elif br and str(br).strip():
        return str(br).strip()
    nested = row.get("appointment_details")
    if isinstance(nested, dict):
        inner = {k: v for k, v in nested.items() if k != "appointment_details"}
        return _branch_label(inner)
    return ""


def _date_part(row: dict) -> str:
    for key in ("date", "appointment_date", "start_date", "appointmentDate"):
        v = row.get(key)
        if v is None:
            continue
        s = str(v).strip()
        if not s:
            continue
        if "T" in s:
            return s.split("T", 1)[0][:10]
        return s[:10]
    return ""


def _time_part(row: dict) -> str:
    for key in ("time", "start_time", "appointment_time", "appointmentTime"):
        v = row.get(key)
        if v is None:
            continue
        s = str(v).strip()
        if s:
            return s
    return ""


def _split_datetime_field(row: dict) -> Tuple[str, str]:
    """Some CRM rows only expose a single ISO datetime string."""
    for key in ("start_datetime", "datetime", "appointment_datetime", "starts_at", "start_at"):
        v = row.get(key)
        if not isinstance(v, str) or "T" not in v:
            continue
        raw = v.replace("Z", "").strip()
        parts = raw.split("T", 1)
        if len(parts) != 2:
            continue
        date_guess = parts[0][:10]
        time_rest = parts[1].split(".")[0].split("+")[0].strip()
        time_guess = time_rest[:5] if len(time_rest) >= 5 else time_rest
        return date_guess, time_guess
    return "", ""


def _support_phone_display() -> str:
    return (config.TRAINER_WHATSAPP_NUMBER or "").strip() or "+961 XX XXXXXX"


def _pick_primary_and_secondary(appointments: List[dict]) -> Tuple[Optional[dict], Optional[dict]]:
    ok = [r for r in appointments if isinstance(r, dict) and _row_ok(r)]
    if not ok:
        ok = [r for r in appointments if isinstance(r, dict)]
    if not ok:
        return None, None

    def sort_key(r: dict) -> str:
        return _date_part(r) or "9999-12-31"

    ok.sort(key=sort_key)
    first = ok[0]
    second = ok[1] if len(ok) > 1 else None
    return first, second


_APPOINTMENT_DRIVEN_KEYS = frozenset(
    {
        "appointment_date",
        "appointment_time",
        "branch_name",
        "service_name",
        "next_appointment_date",
    }
)


async def resolve_real_test_template_placeholders(phone_raw: str) -> Tuple[Dict[str, str], Dict[str, Any]]:
    """
    Build placeholder values for WhatsApp template test sends from CRM.

    Returns:
        (values_by_placeholder_name, meta) — meta includes has_customer, has_appointment, warnings, source.
    """
    meta: Dict[str, Any] = {
        "source": "none",
        "warnings": [],
        "has_customer": False,
        "has_appointment": False,
    }
    vals: Dict[str, str] = {}

    cust_resp = await get_customer_by_phone(phone=phone_raw)
    if isinstance(cust_resp, dict) and cust_resp.get("success") and cust_resp.get("data"):
        meta["has_customer"] = True
        n = _customer_name_from_crm(cust_resp.get("data"))
        if n:
            vals["customer_name"] = n

    primary: Optional[dict] = None
    secondary: Optional[dict] = None

    next_resp = await check_next_appointment(phone=phone_raw)
    if isinstance(next_resp, dict) and next_resp.get("success"):
        apt = _extract_next_appointment_dict(next_resp)
        if isinstance(apt, dict) and apt:
            primary = apt

    if primary is None:
        all_resp = await get_customer_appointments(phone=phone_raw)
        if isinstance(all_resp, dict) and all_resp.get("success"):
            rows = _extract_customer_appointments_list(all_resp)
            primary, secondary = _pick_primary_and_secondary(rows)

    if primary:
        meta["has_appointment"] = True
        meta["source"] = "crm_appointment"
        row = _coalesce_appointment_row(primary)
        if not vals.get("customer_name"):
            cn = str(
                row.get("customer_name")
                or row.get("name")
                or primary.get("customer_name")
                or primary.get("name")
                or ""
            ).strip()
            if cn:
                vals["customer_name"] = cn
        ap_date = _date_part(row)
        ap_time = _time_part(row)
        if not ap_date or not ap_time:
            d2, t2 = _split_datetime_field(row)
            ap_date = ap_date or d2
            ap_time = ap_time or t2
        vals["appointment_date"] = ap_date
        vals["appointment_time"] = ap_time
        vals["branch_name"] = _branch_label(row) or _branch_label(primary)
        vals["service_name"] = _service_label(row) or _service_label(primary)
        next_d = _date_part(_coalesce_appointment_row(secondary)) if secondary else ""
        vals["next_appointment_date"] = next_d or ap_date
    else:
        if meta["has_customer"]:
            meta["source"] = "crm_customer_only"
            meta["warnings"].append(
                "No usable appointment row in CRM for this number — appointment fields cannot be filled."
            )
        else:
            meta["warnings"].append("Phone not found in CRM (customers/by-phone).")

    vals["phone_number"] = _support_phone_display()

    np = normalize_phone(phone_raw)
    meta["normalized_phone"] = np
    meta["recipient_display_phone"] = np or str(phone_raw).strip()

    # Production-aligned defaults for test sends (reminder_24h, sent_17_days_after_last_session_new, …)
    if meta.get("has_appointment"):
        if not str(vals.get("branch_name") or "").strip():
            vals["branch_name"] = "الفرع الرئيسي"
            meta["warnings"].append(
                "branch_name was empty in CRM — using default «الفرع الرئيسي» for test send."
            )
        if not str(vals.get("service_name") or "").strip():
            vals["service_name"] = "جلسة ليزر"
            meta["warnings"].append(
                "service_name was empty in CRM — using default «جلسة ليزر» for test send."
            )

    return vals, meta


def template_needs_appointment_data(template_param_names: List[str], n_body: int) -> bool:
    names = set(template_param_names)
    if names & _APPOINTMENT_DRIVEN_KEYS:
        return True
    # Positional-only body: assume may map to appointment-related content
    if n_body > 0 and not template_param_names:
        return True
    return False


def validate_test_placeholders_for_template(
    template_param_names: List[str],
    n_body: int,
    test_parameters: Dict[str, str],
    meta: Dict[str, Any],
) -> Optional[str]:
    """
    If CRM data is insufficient for this template, return a user-facing error string.
    """
    needs_appt = template_needs_appointment_data(template_param_names, n_body)
    if needs_appt and not meta.get("has_appointment"):
        return (
            "This template needs appointment details (date/time/branch/service). "
            "No upcoming appointment was found in CRM for this phone. "
            "Use a number that has an active booking, or check appointments/customer API."
        )

    def _empty(v: Any) -> bool:
        s = str(v or "").strip()
        return not s or s == "—"

    for param in template_param_names:
        if _empty(test_parameters.get(param)):
            return f"Missing real value for template variable «{param}» from CRM — cannot send an accurate test."

    # Body slots {{1}}..{{n}}: when Monty/Meta exposes named parameters, those map to slots
    # 1..len(names) — smart_messaging_api only adds numeric keys for *extra* slots past the names.
    # Do not require test_parameters["1"] if slot 1 is already covered by template_param_names[0].
    for i in range(n_body):
        k = str(i + 1)
        if template_param_names and i < len(template_param_names):
            continue
        if _empty(test_parameters.get(k)):
            return f"Missing real value for body slot {k} — CRM data incomplete for this template."

    return None
