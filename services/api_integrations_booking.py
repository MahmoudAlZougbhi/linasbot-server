"""Appointment create, discount, and date-update API (LOC split)."""

from __future__ import annotations

import os
from typing import Any

from services.api_integrations_http import _make_api_request, log_report_event
from services.api_integrations_reminders import get_appointment_details
from services.api_integrations_status import _phone_clean_for_appointment_api, resume_appointment


def _clean_body_part_ids_for_api(raw: list | None) -> list[int]:
    out: list[int] = []
    for bid in raw or []:
        try:
            i = int(bid)
            if i > 0:
                out.append(i)
        except (TypeError, ValueError):
            continue
    return out


def _body_part_session_row(body_part_id: int, session_number: int = 1) -> dict:
    """
    Official Appointment API (BOC): body_parts[] uses **id** + session_number.
    LINASLASER_BODY_PARTS_ITEM_ID_KEY: default `id`; use `body_part_id` for legacy stacks;
    `both` sends id and body_part_id with the same value.
    """
    sn = int(session_number)
    if sn < 1:
        sn = 1
    pid = int(body_part_id)
    key = (os.getenv("LINASLASER_BODY_PARTS_ITEM_ID_KEY") or "id").strip().lower() or "id"
    if key in ("both", "dual"):
        return {"id": pid, "body_part_id": pid, "session_number": sn}
    if key in ("body_part_id", "legacy", "old"):
        return {"body_part_id": pid, "session_number": sn}
    return {"id": pid, "session_number": sn}


def _clean_body_parts_with_sessions_for_api(raw: Any) -> list[Any]:
    """Normalize list items to BOC body_parts rows (default key **id** per API doc)."""
    out: list[Any] = []
    if not isinstance(raw, list) or not raw:
        return out
    for item in raw:
        if not isinstance(item, dict):
            continue
        raw_id = item.get("body_part_id")
        if raw_id is None:
            raw_id = item.get("id")
        if raw_id is None:
            continue
        try:
            pid = int(raw_id)
        except (TypeError, ValueError):
            continue
        if pid <= 0:
            continue
        try:
            sn = int(item.get("session_number", 1))
        except (TypeError, ValueError):
            sn = 1
        out.append(_body_part_session_row(pid, sn))
    return out


async def create_appointment(
    phone: str,
    service_id: int,
    branch_id: int,
    date: str,
    machine_id: int | None = None,
    user_code: str | None = None,
    body_part_ids: list | None = None,
    body_parts_with_sessions: list | None = None,
    **kwargs: Any,
) -> Any:
    """
    POST appointments/create.

    Default: when **body_parts_with_sessions** is non-empty, sends **body_parts** (BOC team contract:
    one row per area with session_number). Set **LINASLASER_APPOINTMENT_BODY_PART_IDS_ONLY=1** to
    send only top-level **body_part_ids** when every session is 1 (legacy).

    **LINASLASER_CREATE_APPOINTMENT_LEGACY_BODY_PARTS** / **LINASLASER_FORCE_BODY_PARTS_WITH_SESSIONS**
    still force the body_parts shape when combined with ids-only logic for older deployments.
    """
    # Clean phone number to match API expected format (without + prefix and country code)
    phone_clean = str(phone).replace("+", "").replace(" ", "").replace("-", "")
    if phone_clean.startswith("961"):
        phone_clean = phone_clean[3:]  # Remove Lebanon country code

    print(
        f"API Call: create_appointment for phone=***{str(phone_clean)[-4:] if phone_clean else ''} (original_last4=***{str(phone)[-4:] if phone else ''}), service={service_id}, date={date}"
    )
    json_data = {"phone": phone_clean, "service_id": service_id, "branch_id": branch_id, "date": date}
    if machine_id is not None:
        json_data["machine_id"] = machine_id
    if user_code:
        json_data["user_code"] = user_code

    legacy_env = os.getenv("LINASLASER_CREATE_APPOINTMENT_LEGACY_BODY_PARTS", "").lower() in (
        "1",
        "true",
        "yes",
    )
    force_sessions_env = os.getenv("LINASLASER_FORCE_BODY_PARTS_WITH_SESSIONS", "").lower() in (
        "1",
        "true",
        "yes",
    )
    ids_only = os.getenv("LINASLASER_APPOINTMENT_BODY_PART_IDS_ONLY", "").lower() in (
        "1",
        "true",
        "yes",
    )
    ids_from_arg = _clean_body_part_ids_for_api(body_part_ids)
    cleaned_bps = _clean_body_parts_with_sessions_for_api(body_parts_with_sessions)

    use_body_parts = False
    if cleaned_bps:
        non_one = any(int(x.get("session_number", 1)) != 1 for x in cleaned_bps)
        prefer_parts = not ids_only or force_sessions_env or legacy_env or non_one
        if prefer_parts:
            json_data["body_parts"] = cleaned_bps
            use_body_parts = True
        else:
            json_data["body_part_ids"] = [int(x.get("id") or x.get("body_part_id")) for x in cleaned_bps]
    elif legacy_env and ids_from_arg:
        json_data["body_parts"] = [_body_part_session_row(bid, 1) for bid in ids_from_arg]
        use_body_parts = True
    elif ids_from_arg:
        json_data["body_part_ids"] = ids_from_arg

    if use_body_parts:
        print(
            "API Call: create_appointment using body_parts "
            "{id, session_number} (BOC doc; LINASLASER_BODY_PARTS_ITEM_ID_KEY overrides key)"
        )

    response = await _make_api_request("POST", "appointments/create", json_data=json_data)
    if response.get("success"):
        log_report_event(
            "api_call",
            "System",
            "N/A",
            {"api": "create_appointment", "status": "success", "phone": phone, "appointment": response.get("data")},
        )
    else:
        log_report_event(
            "api_call",
            "System",
            "N/A",
            {"api": "create_appointment", "status": "failed", "error": response.get("message"), "phone": phone},
        )
    return response


def _safe_float_amount(v: Any) -> float | None:
    try:
        if v is None or v == "":
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def extract_appointment_total_from_api_payload(payload: Any) -> float | None:
    """
    Best-effort total from get_appointment_details / create_appointment response shapes.
    """
    if not isinstance(payload, dict):
        return None
    data = payload.get("data")
    apt: dict = {}
    if isinstance(data, dict):
        if isinstance(data.get("appointment"), dict):
            apt = data["appointment"]
        else:
            apt = data
    else:
        apt = payload
    if not isinstance(apt, dict):
        return None
    for key in ("total", "total_price", "final_price", "price", "amount"):
        x = _safe_float_amount(apt.get(key))
        if x is not None:
            return x
    pr = apt.get("pricing")
    if isinstance(pr, dict):
        for key in ("total", "total_price", "final_price", "price", "amount"):
            x = _safe_float_amount(pr.get(key))
            if x is not None:
                return x
    return None


async def add_appointment_discount(appointment_id: int, discount_amount: float) -> Any:
    """
    POST appointments/discount/add — applies a discount so CRM total can match an agreed price.

    Body: appointment_id, discount_amount (per Agent API contract).
    """
    try:
        aid = int(appointment_id)
    except (TypeError, ValueError):
        return {"success": False, "message": "invalid_appointment_id"}
    try:
        damount = float(discount_amount)
    except (TypeError, ValueError):
        return {"success": False, "message": "invalid_discount_amount"}
    if damount <= 0:
        return {"success": False, "message": "discount_amount_must_be_positive"}
    json_data = {
        "appointment_id": aid,
        "discount_amount": round(damount, 4),
    }
    print(
        f"API Call: add_appointment_discount for appointment_id={aid}, discount_amount={json_data['discount_amount']}"
    )
    response = await _make_api_request("POST", "appointments/discount/add", json_data=json_data)
    if response.get("success"):
        log_report_event(
            "api_call",
            "System",
            "N/A",
            {"api": "add_appointment_discount", "status": "success", "appointment_id": aid},
        )
    else:
        log_report_event(
            "api_call",
            "System",
            "N/A",
            {
                "api": "add_appointment_discount",
                "status": "failed",
                "error": response.get("message"),
                "appointment_id": aid,
            },
        )
    return response


async def sync_appointment_agreed_price(
    appointment_id: int,
    agreed_price: float,
    system_total_known: float | None = None,
) -> dict[str, Any]:
    """
    Compare CRM appointment total to the price the assistant agreed with the customer.
    If CRM total is higher, calls add_appointment_discount with (crm_total - agreed_price).

    Pass system_total_known when the total was just returned from booking/create and you want to avoid an extra GET.
    """
    try:
        aid = int(appointment_id)
    except (TypeError, ValueError):
        return {"success": False, "message": "invalid_appointment_id", "error_type": "bad_request"}
    try:
        agreed = float(agreed_price)
    except (TypeError, ValueError):
        return {"success": False, "message": "invalid_agreed_price", "error_type": "bad_request"}

    system_total = None
    if system_total_known is not None:
        try:
            system_total = float(system_total_known)
        except (TypeError, ValueError):
            system_total = None

    if system_total is None:
        det = await get_appointment_details(aid)
        if not det.get("success"):
            return {
                "success": False,
                "message": det.get("message") or "get_appointment_details_failed",
                "error_type": "lookup_failed",
                "api_response": det,
            }
        system_total = extract_appointment_total_from_api_payload(det)

    if system_total is None:
        return {
            "success": False,
            "message": "could_not_read_system_price_for_appointment",
            "error_type": "missing_price",
            "appointment_id": aid,
        }

    eps = 0.02
    if abs(system_total - agreed) <= eps:
        return {
            "success": True,
            "skipped": True,
            "message": "crm_total_already_matches_agreed_price",
            "appointment_id": aid,
            "crm_total": system_total,
            "agreed_price": agreed,
        }

    if agreed > system_total + eps:
        return {
            "success": False,
            "message": "agreed_price_exceeds_crm_total_api_does_not_increase_price",
            "error_type": "agreed_above_system",
            "appointment_id": aid,
            "crm_total": system_total,
            "agreed_price": agreed,
        }

    discount_amount = system_total - agreed
    if discount_amount <= eps:
        return {
            "success": True,
            "skipped": True,
            "message": "no_discount_needed",
            "appointment_id": aid,
            "crm_total": system_total,
            "agreed_price": agreed,
        }

    disc_resp = await add_appointment_discount(aid, discount_amount)
    merged = {
        "success": bool(disc_resp.get("success")),
        "appointment_id": aid,
        "crm_total_before": system_total,
        "agreed_price": agreed,
        "discount_amount_applied": round(discount_amount, 4),
        "discount_api_response": disc_resp,
    }
    if not disc_resp.get("success"):
        merged["message"] = disc_resp.get("message") or "discount_api_failed"
        merged["error_type"] = "discount_api_failed"
    else:
        merged["message"] = "discount_applied_to_match_agreed_price"
    return merged


async def update_appointment_date(appointment_id: int, phone: str, date: str, user_code: str | None = None) -> Any:
    """Updates the date/time of an existing appointment."""
    phone_clean = _phone_clean_for_appointment_api(phone)

    print(
        f"API Call: update_appointment_date for appointment_id={appointment_id}, phone=***{str(phone_clean)[-4:] if phone_clean else ''} (original_last4=***{str(phone)[-4:] if phone else ''}), date={date}"
    )
    json_data = {"appointment_id": appointment_id, "phone": phone_clean, "date": date}
    if user_code:
        json_data["user_code"] = user_code
    # : same-request hint for CRMs that clear pause when this field is present (confirm with Agent API spec).
    if os.getenv("LINASLASER_UPDATE_DATE_SET_STATUS_AVAILABLE", "").lower() in ("1", "true", "yes"):
        json_data["status"] = "Available"

    response = await _make_api_request("POST", "appointments/update/date", json_data=json_data)
    if response.get("success"):
        log_report_event(
            "api_call",
            "System",
            "N/A",
            {
                "api": "update_appointment_date",
                "status": "success",
                "phone": phone,
                "appointment_id": appointment_id,
                "new_date": date,
            },
        )
        # After reschedule: Paused→Available via CRM POST /api/appointments/update-status (see resume_appointment).
        resume_resp = await resume_appointment(phone, appointment_id)
        response = dict(response)
        if resume_resp.get("skipped"):
            response["resume_appointment"] = {"attempted": False, "skipped": True}
        else:
            response["resume_appointment"] = {
                "attempted": True,
                "success": bool(resume_resp.get("success")),
                "skipped": False,
                "message": resume_resp.get("message"),
                "path": resume_resp.get("path"),
            }
    else:
        log_report_event(
            "api_call",
            "System",
            "N/A",
            {
                "api": "update_appointment_date",
                "status": "failed",
                "error": response.get("message"),
                "phone": phone,
                "appointment_id": appointment_id,
            },
        )
    return response
