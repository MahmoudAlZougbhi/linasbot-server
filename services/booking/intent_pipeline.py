# -*- coding: utf-8 -*-
"""
Strict booking pipeline: AI submits extraction JSON → backend validates → CRM create only when valid.

All CRM creates for new appointments go through `finalize_crm_booking_tool_output` (shared with the
legacy `create_appointment` tool path). The model must not treat a booking as confirmed unless the
tool result has success and booking_flow_state=booked (with api_response from the CRM).
"""

from __future__ import annotations

import copy
import datetime
import json
import os
from typing import Any, Dict, List, Optional, Set, Tuple

import config
from services import api_integrations
from services.booking.constants import (
    BEIRUT_BRANCH_ID,
    BOOKING_TIMEZONE_LABEL,
    DEFAULT_BODY_PART_REQUIRED_SERVICE_IDS,
    HAIR_REMOVAL_MACHINE_IDS,
    LASER_HAIR_REMOVAL_SERVICE_IDS,
    MACHINE_OPTIONAL_SERVICE_IDS,
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
from services.booking.strict_ids import (
    strict_validate_branch_id,
    strict_validate_machine_id,
    strict_validate_service_id,
)
from services.booking.validation_contract import (
    booking_validation_error,
    CODE_AMBIGUOUS_BOOKING_REQUEST,
    CODE_CUSTOMER_DATA_INCOMPLETE,
    CODE_INVALID_BODY_PART_IDS,
    CODE_INVALID_BRANCH_ID,
    CODE_INVALID_MACHINE_ID,
    CODE_INVALID_SERVICE_ID,
    CODE_MAX_REPAIR_ATTEMPTS_EXCEEDED,
    CODE_MISSING_BODY_PART_IDS,
    CODE_MISSING_REQUIRED_FIELD,
    CODE_TIME_SLOT_UNAVAILABLE,
    CODE_TOOL_DATA_REQUIRED,
)
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


def _coerce_int_id(value: Any) -> Optional[int]:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _merge_body_parts_sessions_from_intent(
    body_ids: List[int],
    raw_bps: Any,
) -> List[Dict[str, int]]:
    """
    Build BOC body_parts list: use model-provided session_number per body_part_id when valid;
    fill missing ids with session_number=1. Order follows body_ids.
    """
    if not body_ids:
        return []
    allowed = {int(b) for b in body_ids}
    by_id: Dict[int, int] = {}
    if isinstance(raw_bps, list) and raw_bps:
        for item in raw_bps:
            if not isinstance(item, dict):
                continue
            pid = _coerce_int_id(item.get("body_part_id") or item.get("id"))
            if pid is None or pid not in allowed:
                continue
            try:
                sn = int(item.get("session_number", 1))
            except (TypeError, ValueError):
                sn = 1
            if sn < 1:
                sn = 1
            by_id[pid] = sn
    out: List[Dict[str, int]] = []
    for bid in body_ids:
        out.append({"body_part_id": int(bid), "session_number": int(by_id.get(bid, 1))})
    return out


def _services_without_machine_from_env() -> Set[int]:
    """
    Optional override for services that should allow booking without machine_id.
    Env example: LINASLASER_SERVICES_WITHOUT_MACHINE_IDS="20,21"
    """
    raw = (os.getenv("LINASLASER_SERVICES_WITHOUT_MACHINE_IDS") or "").strip()
    if not raw:
        return set()
    out: Set[int] = set()
    for tok in raw.split(","):
        try:
            i = int(tok.strip())
            if i > 0:
                out.add(i)
        except (TypeError, ValueError):
            continue
    return out


def _service_requires_machine(service_id: Optional[int]) -> bool:
    """
    Default policy: machine is required unless service is explicitly allowlisted.
    """
    if service_id is None:
        return True
    if service_id in MACHINE_OPTIONAL_SERVICE_IDS:
        return False
    return service_id not in _services_without_machine_from_env()


def _crm_rejection_validation_error(
    norm_vals: Dict[str, Any], api_resp: Dict[str, Any]
) -> Dict[str, Any]:
    api_msg = str(api_resp.get("message") or "").strip()
    inv: Dict[str, Any] = {"calendar": "slot_unavailable_or_conflict"}
    if api_msg:
        inv["api_detail"] = api_msg[:800]
    low = api_msg.lower()
    if any(
        x in low
        for x in (
            "connection",
            "network",
            "timeout",
            "http error",
            "unexpected error",
            "invalid json",
        )
    ):
        hr = (
            "A temporary system or network error occurred while contacting the clinic calendar. "
            "Do not confirm a booking. Ask the user to try again in a moment or offer human assistance."
        )
    else:
        hr = (
            "The clinic calendar could not accept this slot (it may already be taken or blocked). "
            "Do not tell the user the appointment was confirmed. Ask them to pick another time or day "
            "within allowed hours, then call submit_booking_intent again with the updated choice."
        )
    err = validation_error_response(
        invalid_fields=inv,
        normalized_values=norm_vals,
        human_readable_reason=hr,
        suggested_slots=[],
    )
    err["crm_rejection"] = True
    err["api_response"] = api_resp
    return err


async def finalize_crm_booking_tool_output(
    *,
    user_id: str,
    raw_user_message: str,
    ai_extracted: Dict[str, Any],
    norm_vals: Dict[str, Any],
    payload: Dict[str, Any],
    phase: str,
) -> Dict[str, Any]:
    """
    Single CRM create + logging + tool JSON shape for submit_booking_intent and legacy create_appointment.
    """
    api_resp = await api_integrations.create_appointment(**payload)
    ok = bool(api_resp.get("success"))
    st = config.user_booking_state[user_id]

    _log_booking_attempt(
        {
            "phase": phase,
            "raw_user_message": raw_user_message,
            "ai_extracted": ai_extracted,
            "normalized_values": norm_vals,
            "endpoint_called": "POST appointments/create",
            "endpoint_payload": payload,
            "endpoint_response": {"success": ok, "message": api_resp.get("message")},
            "response_category": "booked" if ok else "api_rejected",
        }
    )

    if ok:
        st["booking_flow_state"] = "booked"
        st["booking_validation_failures"] = 0
        st["last_booking_success"] = copy.deepcopy(api_resp.get("data"))
        return {
            "success": True,
            "booking_flow_state": "booked",
            "message": "Booking created in CRM. You may confirm to the user using ONLY these facts from the API response.",
            "normalized_values": norm_vals,
            "api_response": api_resp,
        }

    st["booking_flow_state"] = "validation_failed"
    err = _crm_rejection_validation_error(norm_vals, api_resp)
    st["last_validation_error"] = err
    return err


async def legacy_create_appointment_tool_output(
    *,
    user_id: str,
    function_args: Dict[str, Any],
    current_gender: str,
    user_input: str,
) -> Dict[str, Any]:
    """
    Internal/legacy path: after chat_response_service preprocessing, run the same CRM create + response
    shape as submit_booking_intent (success + api_response wrapper, or validation_error on CRM reject).
    """
    fa = dict(function_args or {})
    sid = _coerce_int_id(fa.get("service_id"))
    bid = _coerce_int_id(fa.get("branch_id"))
    mid = _coerce_int_id(fa.get("machine_id"))
    date_str = str(fa.get("date") or "").strip()
    phone = str(fa.get("phone") or "").strip()

    legacy_body_parts_env = os.getenv("LINASLASER_CREATE_APPOINTMENT_LEGACY_BODY_PARTS", "").lower() in (
        "1",
        "true",
        "yes",
    )
    force_sessions_env = os.getenv("LINASLASER_FORCE_BODY_PARTS_WITH_SESSIONS", "").lower() in (
        "1",
        "true",
        "yes",
    )
    bps = fa.get("body_parts_with_sessions")
    body_ids: List[int] = []
    non_one_session = False
    if isinstance(bps, list) and bps:
        for item in bps:
            if not isinstance(item, dict):
                continue
            pid = _coerce_int_id(item.get("body_part_id") or item.get("id"))
            if pid is not None and pid > 0:
                body_ids.append(pid)
            try:
                sn = int(item.get("session_number", 1))
            except (TypeError, ValueError):
                sn = 1
            if sn != 1:
                non_one_session = True
    else:
        for x in fa.get("body_part_ids") or []:
            pid = _coerce_int_id(x)
            if pid is not None and pid > 0:
                body_ids.append(pid)

    norm_vals: Dict[str, Any] = {
        "service_id": sid,
        "branch_id": bid,
        "machine_id": mid,
        "body_part_ids": body_ids,
        "timezone": BOOKING_TIMEZONE_LABEL,
        "api_date": date_str,
    }

    missing: List[str] = []
    machine_required_legacy = _service_requires_machine(sid)
    if not phone:
        missing.append("phone")
    if sid is None:
        missing.append("service_id")
    if bid is None:
        missing.append("branch_id")
    if machine_required_legacy and mid is None:
        missing.append("machine_id")
    if not date_str:
        missing.append("date")
    if missing:
        st = config.user_booking_state[user_id]
        st["booking_flow_state"] = "validation_failed"
        err = validation_error_response(
            missing_fields=sorted(set(missing)),
            normalized_values=norm_vals,
            human_readable_reason="Incomplete arguments for legacy create_appointment; gather required fields and prefer submit_booking_intent.",
        )
        st["last_validation_error"] = err
        return err

    payload: Dict[str, Any] = {
        "phone": phone,
        "service_id": int(sid),
        "branch_id": int(bid),
        "date": date_str,
    }
    if mid is not None:
        payload["machine_id"] = int(mid)
    uc = fa.get("user_code")
    if uc:
        payload["user_code"] = uc
    # PDF: top-level body_part_ids. Pass body_parts_with_sessions only when the API must
    # preserve session_number (≠1) or when LINASLASER_CREATE_APPOINTMENT_LEGACY_BODY_PARTS is set.
    if force_sessions_env or legacy_body_parts_env or non_one_session:
        if isinstance(bps, list) and bps:
            payload["body_parts_with_sessions"] = bps
        elif body_ids:
            payload["body_part_ids"] = body_ids
    elif body_ids:
        payload["body_part_ids"] = body_ids

    ai_snapshot = {
        "source": "legacy_create_appointment_tool",
        "gender_context": current_gender,
        "user_input_excerpt": (user_input or "")[:240],
    }
    return await finalize_crm_booking_tool_output(
        user_id=user_id,
        raw_user_message=user_input,
        ai_extracted=ai_snapshot,
        norm_vals=norm_vals,
        payload=payload,
        phase="legacy_create_appointment_execute",
    )


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


def _bump_booking_validation_failure(user_id: str) -> None:
    st = config.user_booking_state[user_id]
    st["booking_validation_failures"] = int(st.get("booking_validation_failures", 0)) + 1


def _reset_booking_validation_failures(user_id: str) -> None:
    config.user_booking_state[user_id]["booking_validation_failures"] = 0


async def handle_submit_booking_intent(
    *,
    user_id: str,
    phone: str,
    current_gender: str,
    user_input: str,
    function_args: Dict[str, Any],
) -> Dict[str, Any]:
    """
    AI supplies structured intent; backend validates (no conversational guessing) and executes CRM.
    """
    raw_msg = user_input
    legacy = bool(getattr(config, "BOOKING_LEGACY_INFERENCE", False))
    max_rep = int(getattr(config, "BOOKING_MAX_REPAIR_ATTEMPTS", 5))
    intent = _merge_intent(dict(function_args or {}))
    execute = bool(intent.get("execute_booking", True))
    phone_clean = str(phone or intent.get("phone") or "").strip()
    if not phone_clean:
        err = booking_validation_error(
            code=CODE_MISSING_REQUIRED_FIELD,
            message="Phone is required for booking.",
            missing_fields=["phone"],
            details={"field": "phone"},
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
    if int(st.get("booking_validation_failures", 0)) >= max_rep:
        err = booking_validation_error(
            code=CODE_MAX_REPAIR_ATTEMPTS_EXCEEDED,
            message="Too many failed validation attempts for this booking flow; human handover required.",
            details={"max_attempts": max_rep, "repair_attempts": st.get("booking_validation_failures", 0)},
            handover_to_human=True,
            handover_reason="max_repair_attempts",
        )
        err["repair_attempt"] = int(st.get("booking_validation_failures", 0))
        err["max_repair_attempts"] = max_rep
        st["booking_flow_state"] = "validation_failed"
        st["last_validation_error"] = err
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

    st["booking_flow_state"] = "ready_for_validation"
    st["last_booking_intent"] = copy.deepcopy(intent)

    def _fail(err: Dict[str, Any], *, state: str = "validation_failed") -> Dict[str, Any]:
        _bump_booking_validation_failure(user_id)
        err["repair_attempt"] = int(st.get("booking_validation_failures", 0))
        err["max_repair_attempts"] = max_rep
        st["booking_flow_state"] = state
        st["last_validation_error"] = err
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

    gender_raw = _effective_gender(intent, current_gender)
    if gender_raw == "unknown":
        err = booking_validation_error(
            code=CODE_MISSING_REQUIRED_FIELD,
            message="Gender is required to validate branch/day rules.",
            missing_fields=["gender"],
            normalized_values={"timezone": BOOKING_TIMEZONE_LABEL},
            details={"field": "gender"},
        )
        return _fail(err, state="needs_clarification")

    gender_cap = "Male" if gender_raw == "male" else "Female"

    services = await load_services()
    branches = await load_branches()
    machines = await load_machines()

    allowed_payload = {
        "branches": [{"id": b.get("id"), "name": b.get("name")} for b in branches[:20]],
        "services": [{"id": s.get("id"), "name": s.get("name")} for s in services[:40]],
        "machines": [{"id": m.get("id"), "name": m.get("name")} for m in machines[:40]],
    }

    svc_id: Optional[int] = None
    svc_miss: Optional[str] = None
    br_id: Optional[int] = None
    br_miss: Optional[str] = None
    had_branch_hint = bool(intent.get("branch_name")) or intent.get("branch_id") is not None

    if legacy:
        svc_id, svc_miss = resolve_service_id(
            intent.get("service_name"),
            intent.get("service_id"),
            gender_raw,
            services,
        )
        br_id, br_miss = resolve_branch_id(intent.get("branch_name"), intent.get("branch_id"), branches)
        if br_id is None:
            br_id = int(config.DEFAULT_BRANCH_ID or BEIRUT_BRANCH_ID)
    else:
        svc_id, svc_st = strict_validate_service_id(intent.get("service_id"), services)
        if svc_st == "missing":
            svc_miss = "service_id"
        elif svc_st == "invalid":
            svc_miss = "invalid_service_id"
        br_id, br_st = strict_validate_branch_id(intent.get("branch_id"), branches)
        if br_st == "missing":
            br_miss = "branch_id"
        elif br_st == "invalid":
            br_miss = "invalid_branch_id"

    missing: List[str] = []
    if svc_miss:
        missing.append(svc_miss)
    if legacy:
        if br_miss and had_branch_hint:
            missing.append(br_miss)
    else:
        if br_miss:
            missing.append(br_miss)

    mach_id: Optional[int] = None
    mach_miss: Optional[str] = None
    machine_required = _service_requires_machine(svc_id)

    if legacy:
        if machine_required and svc_id in LASER_HAIR_REMOVAL_SERVICE_IDS:
            mach_id, mach_miss = resolve_machine_id(
                intent.get("machine_name"),
                intent.get("machine_id"),
                machines,
            )
            if mach_miss:
                missing.append(mach_miss)
        elif machine_required and svc_id == TATTOO_SERVICE_ID:
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
        elif machine_required:
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
        else:
            mach_id = resolve_machine_id(
                intent.get("machine_name"),
                intent.get("machine_id"),
                machines,
            )[0]
    else:
        if machine_required:
            mach_id, mst = strict_validate_machine_id(intent.get("machine_id"), machines)
            if mst == "missing":
                missing.append("machine_id")
            elif mst == "invalid":
                missing.append("invalid_machine_id")
        else:
            mid_opt = _coerce_int_id(intent.get("machine_id"))
            if mid_opt is not None:
                mach_id, mst = strict_validate_machine_id(mid_opt, machines)
                if mst == "invalid":
                    missing.append("invalid_machine_id")

    if legacy and svc_id == TATTOO_SERVICE_ID and not str(intent.get("body_part") or "").strip():
        um = (raw_msg or "").lower()
        if any(
            tok in um
            for tok in (
                "ra2be",
                "ra2bet",
                "ra2bte",
                "رقبة",
                "رقبت",
                "neck",
                "عنق",
                "3an2",
            )
        ):
            intent = dict(intent)
            intent["body_part"] = (raw_msg or "").strip()[:280]

    body_ids: List[int] = []
    bp_miss: Optional[str] = None
    bp_details: Optional[Dict[str, Any]] = None
    if svc_id is not None:
        explicit = intent.get("body_part_ids")
        if isinstance(explicit, list) and explicit:
            body_ids, bp_miss, bp_details = await resolve_body_part_ids(
                svc_id, intent.get("body_part"), explicit, mach_id
            )
        else:
            body_ids, bp_miss, bp_details = await resolve_body_part_ids(
                svc_id, intent.get("body_part"), None, mach_id
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

    if legacy and svc_id is not None and user_input:
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
        "machine_required": machine_required,
        "body_part_ids": body_ids,
        "timezone": BOOKING_TIMEZONE_LABEL,
    }
    if dt_local is not None:
        norm_vals["api_date"] = dt_local.astimezone(BOT_FIXED_TZ).strftime("%Y-%m-%d %H:%M:%S")

    if bp_miss == "invalid_body_part_ids" and bp_details:
        err = booking_validation_error(
            code=CODE_INVALID_BODY_PART_IDS,
            message="One or more body_part_ids are not valid for this service.",
            details=bp_details,
            allowed_values=allowed_payload,
            normalized_values=norm_vals,
        )
        if ambiguities:
            err["ambiguities"] = ambiguities
        return _fail(err)

    if missing or conflicts:
        code = CODE_AMBIGUOUS_BOOKING_REQUEST if conflicts else CODE_MISSING_REQUIRED_FIELD
        if "invalid_service_id" in missing:
            code = CODE_INVALID_SERVICE_ID
        if "invalid_branch_id" in missing:
            code = CODE_INVALID_BRANCH_ID
        if "invalid_machine_id" in missing:
            code = CODE_INVALID_MACHINE_ID
        err = booking_validation_error(
            code=code,
            message="Resolve missing or conflicting structured fields; use tools to fetch ids — do not rely on server guessing.",
            missing_fields=sorted(set(missing)),
            invalid_fields=invalid,
            conflicting_fields=conflicts,
            allowed_values=allowed_payload,
            normalized_values=norm_vals,
            details={"legacy_inference": legacy},
        )
        if ambiguities:
            err["ambiguities"] = ambiguities
        return _fail(err)

    assert svc_id is not None and br_id is not None and dt_local is not None

    if svc_id in DEFAULT_BODY_PART_REQUIRED_SERVICE_IDS and not body_ids:
        err = booking_validation_error(
            code=CODE_MISSING_BODY_PART_IDS,
            message="body_part_ids are required for this service (from get_body_parts).",
            missing_fields=["body_part_ids"],
            normalized_values=norm_vals,
            details={"service_id": svc_id, "expected_source": "get_body_parts"},
        )
        return _fail(err)

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
            err = booking_validation_error(
                code=CODE_TIME_SLOT_UNAVAILABLE,
                message=sv.get("explanation_en", "Slot not allowed for this service/branch/gender."),
                invalid_fields={"slot": sv.get("code")},
                normalized_values=norm_vals,
                slot_validation=sv,
                suggested_slots=[],
                details={"slot_validation": sv},
            )
            return _fail(err)

    customer_name = intent.get("customer_name") or config.user_names.get(user_id, "")
    ok_cust, cust_err = await _ensure_customer(phone_clean, customer_name or None, gender_cap)
    if not ok_cust:
        err = booking_validation_error(
            code=CODE_CUSTOMER_DATA_INCOMPLETE,
            message=cust_err or "Could not ensure customer record.",
            missing_fields=["customer_name"] if "name" in (cust_err or "") else [],
            normalized_values=norm_vals,
        )
        return _fail(err, state="needs_clarification")

    if not execute:
        shell = success_validation_shell(
            normalized_values=norm_vals,
            booking_flow_state="ready_to_book",
        )
        shell["message"] = "Validation passed; execute_booking=false so CRM was not called."
        shell["status"] = "success"
        st["booking_flow_state"] = "ready_to_book"
        _reset_booking_validation_failures(user_id)
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

    payload_bps = _merge_body_parts_sessions_from_intent(
        body_ids, intent.get("body_parts_with_sessions")
    )
    payload = {
        "phone": phone_clean,
        "service_id": svc_id,
        "branch_id": br_id,
        "date": api_date,
        "body_part_ids": body_ids,
        "body_parts_with_sessions": payload_bps,
    }
    if mach_id is not None:
        payload["machine_id"] = mach_id
    return await finalize_crm_booking_tool_output(
        user_id=user_id,
        raw_user_message=raw_msg,
        ai_extracted=intent,
        norm_vals=norm_vals,
        payload=payload,
        phase="submit_booking_intent_execute",
    )
