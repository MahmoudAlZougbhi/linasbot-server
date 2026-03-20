# -*- coding: utf-8 -*-
"""
Strict booking pipeline: AI submits extraction JSON → backend validates → optional create_appointment.

The model must not treat a booking as confirmed unless this pipeline returns API success.
"""

from __future__ import annotations

import copy
import json
import datetime
from typing import Any, Dict, List, Optional, Tuple

import config
from services import api_integrations
from services.booking.constants import (
    BEIRUT_BRANCH_ID,
    BOOKING_TIMEZONE_LABEL,
    DEFAULT_BODY_PART_REQUIRED_SERVICE_IDS,
    HAIR_REMOVAL_MACHINE_IDS,
    LASER_HAIR_REMOVAL_SERVICE_IDS,
    TATTOO_SERVICE_ID,
)
from services.booking.resolver import (
    is_pico_machine,
    load_branches,
    load_machines,
    load_services,
    machine_label_for,
    pick_default_machine_for_non_hair,
    pick_pico_or_default_machine,
    resolve_body_part_ids,
    resolve_branch_id,
    resolve_machine_id,
    resolve_service_id,
)
from services.booking.schemas import empty_booking_intent_template, success_validation_shell, validation_error_response
from services.booking_service_mapping import validate_service_mapping_from_text
from utils.appointment_slot_rules import parse_normalized_api_datetime, validate_booking_slot
from utils.datetime_utils import (
    BOT_FIXED_TZ,
    align_datetime_to_day_reference,
    datetime_from_ai_date_components,
    now_in_bot_tz,
    parse_datetime_flexible,
)


def _log_booking_attempt(payload: Dict[str, Any]) -> None:
    try:
        line = json.dumps(payload, default=str, ensure_ascii=False)
    except (TypeError, ValueError):
        line = str(payload)
    print(f"[BOOKING_PIPELINE] {line[:12000]}")


def _merge_intent(function_args: Dict[str, Any]) -> Dict[str, Any]:
    base = empty_booking_intent_template()
    fa = dict(function_args or {})
    for k in list(base.keys()):
        if fa.get(k) is not None:
            base[k] = fa[k]
    return base


def _effective_gender(intent: Dict[str, Any], current_gender: str) -> str:
    g = intent.get("gender") or current_gender
    return (g or "unknown").strip().lower()


def _build_api_datetime(intent: Dict[str, Any]) -> Tuple[Optional[datetime.datetime], List[str], List[str]]:
    """Return (aware datetime in BOT tz, missing field tokens, ambiguity tokens)."""
    missing: List[str] = []
    amb: List[str] = []
    now = now_in_bot_tz()

    dt: Optional[datetime.datetime] = None
    dc = intent.get("date_components")
    if isinstance(dc, dict):
        dt = datetime_from_ai_date_components(dc)

    if dt is None:
        nd = intent.get("normalized_date")
        nt = intent.get("normalized_time") or ""
        if nd:
            comb = f"{nd} {nt}".strip()
            dt = parse_datetime_flexible(comb)

    if dt is None and intent.get("date"):
        dt = parse_datetime_flexible(str(intent["date"]))

    if dt is None:
        raw_d = intent.get("raw_user_date_text") or ""
        raw_t = intent.get("raw_user_time_text") or ""
        if str(raw_d).strip() or str(raw_t).strip():
            dt = parse_datetime_flexible(f"{raw_d} {raw_t}".strip())

    ci = (intent.get("calendar_day_intent") or "").strip().lower()
    if dt is not None and ci in ("today", "tomorrow"):
        dt = align_datetime_to_day_reference(dt, ci, reference=now)

    if dt is None:
        missing.append("date_time")
        amb.append("date_time_unresolved")
        return None, missing, amb

    if dt <= now:
        missing.append("date_time")
        amb.append("date_in_past_or_now")

    return dt, missing, amb


async def _ensure_customer(
    phone: str,
    customer_name: Optional[str],
    gender_capitalized: str,
) -> Tuple[bool, Optional[str]]:
    r = await api_integrations.get_customer_by_phone(phone=phone)
    if r.get("success") and r.get("data"):
        return True, None
    if not customer_name or not gender_capitalized:
        return False, "new_customer_requires_name_and_gender"
    cr = await api_integrations.create_customer(
        name=customer_name,
        phone=phone,
        gender=gender_capitalized,
        branch_id=config.DEFAULT_BRANCH_ID,
    )
    if cr.get("success"):
        return True, None
    return False, str(cr.get("message") or "create_customer_failed")


async def handle_submit_booking_intent(
    *,
    user_id: str,
    phone: str,
    current_gender: str,
    user_input: str,
    function_args: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Run full validation and optionally execute create_appointment.

    Returns a dict suitable for JSON tool output to the model.
    """
    raw_msg = user_input
    intent = _merge_intent(dict(function_args or {}))
    execute = bool(intent.get("execute_booking", True))
    phone_clean = str(phone or intent.get("phone") or "").strip()
    if not phone_clean:
        err = validation_error_response(
            missing_fields=["phone"],
            human_readable_reason="Phone is required for booking.",
        )
        _log_booking_attempt(
            {
                "phase": "submit_booking_intent",
                "raw_user_message": raw_msg,
                "ai_extracted": intent,
                "validation": err,
                "endpoint_called": None,
            }
        )
        return err

    st = config.user_booking_state[user_id]
    st["booking_flow_state"] = "ready_for_validation"
    st["last_booking_intent"] = copy.deepcopy(intent)

    gender_raw = _effective_gender(intent, current_gender)
    if gender_raw == "unknown":
        err = validation_error_response(
            missing_fields=["gender"],
            human_readable_reason="Gender is required to validate branch/day rules.",
            normalized_values={"timezone": BOOKING_TIMEZONE_LABEL},
        )
        st["booking_flow_state"] = "needs_clarification"
        _log_booking_attempt(
            {
                "phase": "submit_booking_intent",
                "raw_user_message": raw_msg,
                "ai_extracted": intent,
                "validation": err,
                "endpoint_called": None,
            }
        )
        return err

    gender_cap = "Male" if gender_raw == "male" else "Female"

    services = await load_services()
    branches = await load_branches()
    machines = await load_machines()

    svc_id, svc_miss = resolve_service_id(
        intent.get("service_name"),
        intent.get("service_id"),
        gender_raw,
        services,
    )
    br_id, br_miss = resolve_branch_id(intent.get("branch_name"), intent.get("branch_id"), branches)
    had_branch_hint = bool(intent.get("branch_name")) or intent.get("branch_id") is not None
    if br_id is None:
        br_id = int(config.DEFAULT_BRANCH_ID or BEIRUT_BRANCH_ID)

    missing: List[str] = []
    if svc_miss:
        missing.append(svc_miss)
    if br_miss and had_branch_hint:
        missing.append(br_miss)

    mach_id: Optional[int] = None
    mach_miss: Optional[str] = None
    if svc_id in LASER_HAIR_REMOVAL_SERVICE_IDS:
        mach_id, mach_miss = resolve_machine_id(
            intent.get("machine_name"),
            intent.get("machine_id"),
            machines,
        )
        if mach_miss:
            missing.append(mach_miss)
    elif svc_id == TATTOO_SERVICE_ID:
        mach_id, _ = resolve_machine_id(
            intent.get("machine_name"),
            intent.get("machine_id"),
            machines,
        )
        if mach_id is None or not is_pico_machine(mach_id, machines):
            mach_id = pick_pico_or_default_machine(machines)
        if mach_id is None:
            missing.append("machine")
            mach_miss = "machine"
    else:
        mach_id = resolve_machine_id(
            intent.get("machine_name"),
            intent.get("machine_id"),
            machines,
        )[0]
        if mach_id is None:
            mach_id = pick_default_machine_for_non_hair(svc_id or 0, machines)
        if mach_id is None:
            missing.append("machine")
            mach_miss = "machine"

    body_ids: List[int] = []
    bp_miss: Optional[str] = None
    if svc_id is not None:
        explicit = intent.get("body_part_ids")
        if isinstance(explicit, list) and explicit:
            body_ids, bp_miss = await resolve_body_part_ids(
                svc_id, intent.get("body_part"), explicit
            )
        else:
            body_ids, bp_miss = await resolve_body_part_ids(
                svc_id, intent.get("body_part"), None
            )
        if bp_miss:
            missing.append(bp_miss)

    dt_local, dt_missing, ambiguities = _build_api_datetime(intent)
    for m in dt_missing:
        if m not in missing:
            missing.append(m)

    if intent.get("needs_clarification"):
        ambiguities.extend([str(x) for x in (intent.get("ambiguities") or [])])

    invalid: Dict[str, Any] = {}
    conflicts: Dict[str, Any] = {}

    if svc_id in LASER_HAIR_REMOVAL_SERVICE_IDS and mach_id is not None:
        if mach_id not in HAIR_REMOVAL_MACHINE_IDS:
            conflicts["machine_service"] = {
                "detail": "Selected machine is not in the allowed hair-removal device set for this bot.",
                "machine_id": mach_id,
                "allowed_machine_ids": sorted(HAIR_REMOVAL_MACHINE_IDS),
            }

    if svc_id is not None and user_input:
        map_chk = validate_service_mapping_from_text(user_input, svc_id)
        if not map_chk.get("is_valid"):
            conflicts["service_text_intent"] = {
                "detail": "User wording suggests a different service family than service_id.",
                "mapping_check": map_chk,
            }

    norm_vals: Dict[str, Any] = {
        "service_id": svc_id,
        "branch_id": br_id,
        "machine_id": mach_id,
        "body_part_ids": body_ids,
        "timezone": BOOKING_TIMEZONE_LABEL,
    }
    if dt_local is not None:
        norm_vals["api_date"] = dt_local.astimezone(BOT_FIXED_TZ).strftime("%Y-%m-%d %H:%M:%S")

    if missing or conflicts:
        err = validation_error_response(
            missing_fields=sorted(set(missing)),
            invalid_fields=invalid,
            conflicting_fields=conflicts,
            allowed_values={
                "branches": [{"id": b.get("id"), "name": b.get("name")} for b in branches[:20]],
                "services": [{"id": s.get("id"), "name": s.get("name")} for s in services[:40]],
                "machines": [{"id": m.get("id"), "name": m.get("name")} for m in machines[:40]],
            },
            normalized_values=norm_vals,
            human_readable_reason="Resolve missing or conflicting fields before booking.",
        )
        if ambiguities:
            err["ambiguities"] = ambiguities
        st["booking_flow_state"] = "validation_failed"
        st["last_validation_error"] = err
        _log_booking_attempt(
            {
                "phase": "submit_booking_intent",
                "raw_user_message": raw_msg,
                "ai_extracted": intent,
                "normalized_values": norm_vals,
                "validation": err,
                "endpoint_called": None,
            }
        )
        return err

    assert svc_id is not None and br_id is not None and mach_id is not None and dt_local is not None

    if svc_id in DEFAULT_BODY_PART_REQUIRED_SERVICE_IDS and not body_ids:
        err = validation_error_response(
            missing_fields=["body_part"],
            normalized_values=norm_vals,
            human_readable_reason="body_part_ids required for this service.",
        )
        st["booking_flow_state"] = "validation_failed"
        _log_booking_attempt(
            {
                "phase": "submit_booking_intent",
                "raw_user_message": raw_msg,
                "ai_extracted": intent,
                "validation": err,
                "endpoint_called": None,
            }
        )
        return err

    api_date = norm_vals["api_date"]
    dt_for_slot = parse_normalized_api_datetime(api_date, BOT_FIXED_TZ)
    if dt_for_slot:
        vr = validate_booking_slot(
            dt_local=dt_for_slot,
            service_id=svc_id,
            branch_id=br_id,
            machine_id=mach_id,
            gender_raw=gender_raw,
        )
        if not vr.get("ok"):
            sv = vr.get("slot_validation") or {}
            err = validation_error_response(
                invalid_fields={"slot": sv.get("code")},
                normalized_values=norm_vals,
                human_readable_reason=sv.get("explanation_en", "Slot not allowed for this service/branch/gender."),
                slot_validation=sv,
                suggested_slots=[],
            )
            st["booking_flow_state"] = "validation_failed"
            _log_booking_attempt(
                {
                    "phase": "submit_booking_intent",
                    "raw_user_message": raw_msg,
                    "ai_extracted": intent,
                    "validation": err,
                    "endpoint_called": None,
                }
            )
            return err

    customer_name = intent.get("customer_name") or config.user_names.get(user_id, "")
    ok_cust, cust_err = await _ensure_customer(phone_clean, customer_name or None, gender_cap)
    if not ok_cust:
        err = validation_error_response(
            missing_fields=["customer_name"] if "name" in (cust_err or "") else [],
            human_readable_reason=cust_err or "Could not ensure customer record.",
            normalized_values=norm_vals,
        )
        st["booking_flow_state"] = "needs_clarification"
        _log_booking_attempt(
            {
                "phase": "submit_booking_intent",
                "raw_user_message": raw_msg,
                "ai_extracted": intent,
                "validation": err,
                "endpoint_called": None,
            }
        )
        return err

    if not execute:
        shell = success_validation_shell(
            normalized_values=norm_vals,
            booking_flow_state="ready_to_book",
        )
        shell["message"] = "Validation passed; execute_booking=false so CRM was not called."
        st["booking_flow_state"] = "ready_to_book"
        _log_booking_attempt(
            {
                "phase": "submit_booking_intent",
                "raw_user_message": raw_msg,
                "ai_extracted": intent,
                "normalized_values": norm_vals,
                "validation": shell,
                "endpoint_called": None,
            }
        )
        return shell

    payload = {
        "phone": phone_clean,
        "service_id": svc_id,
        "machine_id": mach_id,
        "branch_id": br_id,
        "date": api_date,
        "body_part_ids": body_ids,
    }
    api_resp = await api_integrations.create_appointment(**payload)
    ok = bool(api_resp.get("success"))

    _log_booking_attempt(
        {
            "phase": "submit_booking_intent_execute",
            "raw_user_message": raw_msg,
            "ai_extracted": intent,
            "normalized_values": norm_vals,
            "endpoint_called": "POST appointments/create",
            "endpoint_payload": payload,
            "endpoint_response": {"success": ok, "message": api_resp.get("message")},
            "response_category": "booked" if ok else "api_rejected",
        }
    )

    if ok:
        st["booking_flow_state"] = "booked"
        st["last_booking_success"] = copy.deepcopy(api_resp.get("data"))
        return {
            "success": True,
            "booking_flow_state": "booked",
            "message": "Booking created in CRM. You may confirm to the user using ONLY these facts from the API response.",
            "normalized_values": norm_vals,
            "api_response": api_resp,
        }

    st["booking_flow_state"] = "validation_failed"
    err = validation_error_response(
        human_readable_reason=str(api_resp.get("message") or "API rejected booking."),
        normalized_values=norm_vals,
        invalid_fields={"api": api_resp.get("message")},
    )
    err["api_response"] = api_resp
    return err
