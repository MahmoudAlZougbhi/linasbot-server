# -*- coding: utf-8 -*-
"""
Strict booking pipeline: AI submits extraction JSON → backend validates → CRM create only when valid.

By default (BOOKING_BACKEND_RESOLVES_NAMES=false) the backend does not map names to IDs — the AI must
supply CRM ids from get_* tools before submit_booking_intent. Set LINASLASER_BOOKING_BACKEND_RESOLVES_NAMES=true
for legacy server-side fuzzy resolution.

All CRM creates for new appointments go through `finalize_crm_booking_tool_output` (shared with the
legacy `create_appointment` tool path). The model must not treat a booking as confirmed unless the
tool result has success and booking_flow_state=booked (with api_response from the CRM).
"""

from __future__ import annotations

import copy
import datetime
import json
import os
import re
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


def _ai_intent_summary(intent: Dict[str, Any]) -> Dict[str, Any]:
    """Condensed extraction snapshot for activity_trace (IDs, names, date hints)."""
    if not intent:
        return {}
    return {
        "service_id": intent.get("service_id"),
        "service_name": intent.get("service_name"),
        "branch_id": intent.get("branch_id"),
        "branch_name": intent.get("branch_name"),
        "machine_id": intent.get("machine_id"),
        "machine_name": intent.get("machine_name"),
        "body_part_ids": intent.get("body_part_ids"),
        "body_part_text": (str(intent.get("body_part") or "").strip()[:400] or None),
        "date": intent.get("date"),
        "time": intent.get("time"),
        "normalized_date": intent.get("normalized_date"),
        "normalized_time": intent.get("normalized_time"),
        "raw_user_date_text": intent.get("raw_user_date_text"),
        "raw_user_time_text": intent.get("raw_user_time_text"),
        "date_components": intent.get("date_components"),
        "calendar_day_intent": intent.get("calendar_day_intent"),
        "execute_booking": intent.get("execute_booking"),
        "needs_clarification": intent.get("needs_clarification"),
    }


def _infer_primary_failure_stage(
    *,
    missing: List[str],
    conflicts: Dict[str, Any],
    invalid: Dict[str, Any],
    backend_resolves: bool,
) -> str:
    """Single primary stage for dashboards (most blocking issue first)."""
    m = set(missing or [])
    if "phone" in m:
        return "phone_required"
    if "gender" in m:
        return "gender_required"
    if "date_time" in m or "resolved_datetime" in m:
        return "date_time_normalization"
    if "service_id" in m:
        return "service_lookup" if backend_resolves else "service_id_resolution"
    if conflicts.get("service_id") or conflicts.get("service_text_intent"):
        return "service_lookup" if backend_resolves else "service_id_resolution"
    if "branch_id" in m:
        return "branch_lookup" if backend_resolves else "branch_id_resolution"
    if conflicts.get("branch_id"):
        return "branch_lookup" if backend_resolves else "branch_id_resolution"
    if "machine_id" in m or conflicts.get("machine_service"):
        return "machine_lookup" if backend_resolves else "machine_id_resolution"
    if "body_part_ids" in m or "body_part" in m:
        return "body_part_lookup"
    if invalid.get("slot") is not None or (invalid or {}).get("calendar"):
        return "backend_validation"
    return "booking_field_extraction"


def _build_booking_activity_trace(
    *,
    failure_stage: str,
    execution_phase: str,
    backend_resolves_names: bool,
    intent: Dict[str, Any],
    detail: str = "",
    missing_fields: Optional[List[str]] = None,
    conflicting_fields: Optional[Dict[str, Any]] = None,
    invalid_fields: Optional[Dict[str, Any]] = None,
    ambiguities: Optional[List[str]] = None,
    datetime_resolution_source: Optional[str] = None,
    normalized_values_snapshot: Optional[Dict[str, Any]] = None,
    pipeline_phase: str = "submit_booking_intent",
    slot_validation: Optional[Dict[str, Any]] = None,
    customer_error: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Structured observability for activity flow: stage, pre/post execution, inputs, missing IDs.
    execution_phase: pre_execution | during_execution
    """
    pre_exec = execution_phase == "pre_execution"
    trace: Dict[str, Any] = {
        "pipeline_phase": pipeline_phase,
        "failure_stage": failure_stage,
        "execution_phase": execution_phase,
        "pre_execution": pre_exec,
        "during_execution": not pre_exec,
        "backend_resolves_names": backend_resolves_names,
        "executor_only_mode": not backend_resolves_names,
        "detail": detail,
        "ai_intent_summary": _ai_intent_summary(intent),
    }
    if missing_fields:
        trace["missing_fields"] = list(missing_fields)
    if conflicting_fields:
        trace["conflicting_fields"] = dict(conflicting_fields)
    if invalid_fields:
        trace["invalid_fields"] = dict(invalid_fields)
    if ambiguities:
        trace["ambiguities"] = list(ambiguities)
    if datetime_resolution_source:
        trace["datetime_resolution_source"] = datetime_resolution_source
    if normalized_values_snapshot is not None:
        trace["normalized_values_snapshot"] = normalized_values_snapshot
    if slot_validation:
        trace["slot_validation"] = slot_validation
    if customer_error:
        trace["customer_error"] = customer_error
    return trace


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


_DATE_ONLY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _build_api_datetime(
    intent: Dict[str, Any],
) -> Tuple[Optional[datetime.datetime], List[str], List[str], str]:
    """
    Build one aware datetime in BOT tz for CRM execution.

    Priority (source of truth for execution — not raw NL alone):
    1) date_components (civil Y/M/D + time)
    2) date as full datetime string, OR date (YYYY-MM-DD) + time / normalized_time
    3) normalized_date + normalized_time or time
    4) Legacy: raw_user_date_text + raw_user_time_text (traceability / backward compat)

    calendar_day_intent is applied only for the legacy_raw path (relative NL), not when an explicit
    absolute date/time was already provided.

    Returns (dt, missing, ambiguities, resolution_source) where resolution_source is one of:
    explicit | normalized | legacy_raw | unresolved
    """
    missing: List[str] = []
    amb: List[str] = []
    now = now_in_bot_tz()
    dt: Optional[datetime.datetime] = None
    resolution_source = "unresolved"

    dc = intent.get("date_components")
    if isinstance(dc, dict):
        dt = datetime_from_ai_date_components(dc)
        if dt is not None:
            resolution_source = "explicit"

    date_val = intent.get("date")
    time_val = intent.get("time")
    nt_norm = intent.get("normalized_time") or ""

    if dt is None and date_val is not None and str(date_val).strip():
        ds = str(date_val).strip()
        if len(ds) > 10 or " " in ds or "T" in ds.lower():
            dt = parse_datetime_flexible(ds)
            if dt is not None:
                resolution_source = "explicit"
        elif _DATE_ONLY_RE.match(ds):
            tv = ""
            if time_val is not None and str(time_val).strip():
                tv = str(time_val).strip()
            elif nt_norm:
                tv = str(nt_norm).strip()
            if tv:
                dt = parse_datetime_flexible(f"{ds} {tv}")
                if dt is not None:
                    resolution_source = "explicit"

    if dt is None:
        nd = intent.get("normalized_date")
        nt = intent.get("normalized_time")
        if time_val is not None and str(time_val).strip():
            nt = time_val
        if nd and str(nd).strip():
            comb = f"{str(nd).strip()} {str(nt or '').strip()}".strip()
            dt = parse_datetime_flexible(comb)
            if dt is not None:
                resolution_source = "normalized"

    if dt is None:
        raw_d = intent.get("raw_user_date_text") or ""
        raw_t = intent.get("raw_user_time_text") or ""
        if str(raw_d).strip() or str(raw_t).strip():
            dt = parse_datetime_flexible(f"{raw_d} {raw_t}".strip())
            if dt is not None:
                resolution_source = "legacy_raw"

    ci = (intent.get("calendar_day_intent") or "").strip().lower()
    if dt is not None and ci in ("today", "tomorrow") and resolution_source == "legacy_raw":
        dt = align_datetime_to_day_reference(dt, ci, reference=now)

    if dt is None:
        missing.append("date_time")
        amb.append("date_time_unresolved")
        return None, missing, amb, "unresolved"

    if dt <= now:
        missing.append("date_time")
        amb.append("date_in_past_or_now")

    return dt, missing, amb, resolution_source


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
    norm_vals: Dict[str, Any],
    api_resp: Dict[str, Any],
    *,
    endpoint_payload: Optional[Dict[str, Any]] = None,
    pipeline_phase: str = "submit_booking_intent_execute",
    ai_extracted: Optional[Dict[str, Any]] = None,
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
        failure_kind = "crm_transport_or_server_error"
        hr = (
            "A temporary system or network error occurred while contacting the clinic calendar. "
            "Do not confirm a booking. Ask the user to try again in a moment or offer human assistance."
        )
    else:
        failure_kind = "crm_business_rejection"
        hr = (
            "The clinic calendar could not accept this slot (it may already be taken or blocked). "
            "Do not tell the user the appointment was confirmed. Ask them to pick another time or day "
            "within allowed hours, then call submit_booking_intent again with the updated choice."
        )
    br = bool(getattr(config, "BOOKING_BACKEND_RESOLVES_NAMES", False))
    payload_summary: Optional[Dict[str, Any]] = None
    if endpoint_payload:
        payload_summary = {
            k: endpoint_payload.get(k)
            for k in (
                "phone",
                "service_id",
                "branch_id",
                "machine_id",
                "date",
                "body_part_ids",
            )
            if k in endpoint_payload
        }
        if "body_parts_with_sessions" in endpoint_payload:
            bps = endpoint_payload.get("body_parts_with_sessions")
            if isinstance(bps, list):
                payload_summary["body_parts_with_sessions_count"] = len(bps)
    trace = _build_booking_activity_trace(
        failure_stage="crm_response",
        execution_phase="during_execution",
        backend_resolves_names=br,
        intent=ai_extracted or {},
        detail=(
            f"CRM/API returned success=false ({failure_kind}). Message: {api_msg[:500]}"
            if api_msg
            else f"CRM/API returned success=false ({failure_kind})."
        ),
        missing_fields=[],
        conflicting_fields={},
        invalid_fields=inv,
        normalized_values_snapshot=norm_vals,
        pipeline_phase=pipeline_phase,
    )
    trace["crm_failure_kind"] = failure_kind
    trace["api_message"] = api_msg[:2000] if api_msg else None
    trace["api_success_field"] = bool(api_resp.get("success"))
    trace["endpoint_payload_sent"] = payload_summary
    trace["raw_api_response_excerpt"] = json.dumps(api_resp, default=str, ensure_ascii=False)[:4000]
    err = validation_error_response(
        invalid_fields=inv,
        normalized_values=norm_vals,
        human_readable_reason=hr,
        suggested_slots=[],
        activity_trace=trace,
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
        st["last_booking_success"] = copy.deepcopy(api_resp.get("data"))
        payload_summary_ok = {
            k: payload.get(k)
            for k in (
                "phone",
                "service_id",
                "branch_id",
                "date",
                "machine_id",
                "body_part_ids",
            )
            if k in payload
        }
        return {
            "success": True,
            "booking_flow_state": "booked",
            "message": "Booking created in CRM. You may confirm to the user using ONLY these facts from the API response.",
            "normalized_values": norm_vals,
            "api_response": api_resp,
            "activity_trace": {
                "pipeline_phase": phase,
                "failure_stage": None,
                "stage": "crm_response",
                "execution_phase": "during_execution",
                "pre_execution": False,
                "during_execution": True,
                "detail": "CRM create_appointment returned success=true.",
                "endpoint_payload_sent": payload_summary_ok,
                "normalized_values_snapshot": norm_vals,
            },
        }

    st["booking_flow_state"] = "validation_failed"
    err = _crm_rejection_validation_error(
        norm_vals,
        api_resp,
        endpoint_payload=payload,
        pipeline_phase=phase,
        ai_extracted=ai_extracted,
    )
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
        intent_snap = _merge_intent(fa)
        mf = sorted(set(missing))
        primary = _infer_primary_failure_stage(
            missing=mf,
            conflicts={},
            invalid={},
            backend_resolves=False,
        )
        err = validation_error_response(
            missing_fields=mf,
            normalized_values=norm_vals,
            human_readable_reason="Incomplete arguments for legacy create_appointment; gather required fields and prefer submit_booking_intent.",
            activity_trace=_build_booking_activity_trace(
                failure_stage=primary,
                execution_phase="pre_execution",
                backend_resolves_names=False,
                intent=intent_snap,
                detail=f"Legacy create_appointment blocked before CRM: missing {mf}.",
                missing_fields=mf,
                normalized_values_snapshot=norm_vals,
                pipeline_phase="legacy_create_appointment_validation",
            ),
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
    backend_resolves = bool(getattr(config, "BOOKING_BACKEND_RESOLVES_NAMES", False))
    if not phone_clean:
        err = validation_error_response(
            missing_fields=["phone"],
            human_readable_reason="Phone is required for booking.",
            activity_trace=_build_booking_activity_trace(
                failure_stage="phone_required",
                execution_phase="pre_execution",
                backend_resolves_names=backend_resolves,
                intent=intent,
                detail="No phone on file and submit_booking_intent did not include phone.",
                missing_fields=["phone"],
                pipeline_phase="submit_booking_intent",
            ),
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
            activity_trace=_build_booking_activity_trace(
                failure_stage="gender_required",
                execution_phase="pre_execution",
                backend_resolves_names=backend_resolves,
                intent=intent,
                detail="User profile gender unknown and intent did not set gender.",
                missing_fields=["gender"],
                normalized_values_snapshot={"timezone": BOOKING_TIMEZONE_LABEL},
                pipeline_phase="submit_booking_intent",
            ),
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

    missing: List[str] = []
    conflicts: Dict[str, Any] = {}
    svc_id: Optional[int] = None
    br_id: Optional[int] = None
    mach_id: Optional[int] = None
    mach_miss: Optional[str] = None
    body_ids: List[int] = []
    had_branch_hint = bool(intent.get("branch_name")) or intent.get("branch_id") is not None

    if backend_resolves:
        svc_miss: Optional[str]
        svc_id, svc_miss = resolve_service_id(
            intent.get("service_name"),
            intent.get("service_id"),
            gender_raw,
            services,
        )
        br_miss: Optional[str]
        br_id, br_miss = resolve_branch_id(intent.get("branch_name"), intent.get("branch_id"), branches)
        if br_id is None:
            br_id = int(config.DEFAULT_BRANCH_ID or BEIRUT_BRANCH_ID)
        if svc_miss:
            missing.append(svc_miss)
        if br_miss and had_branch_hint:
            missing.append(br_miss)

        machine_required = _service_requires_machine(svc_id)
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
                missing.append("machine_id")
                mach_miss = "machine_id"
        elif machine_required:
            mach_id = resolve_machine_id(
                intent.get("machine_name"),
                intent.get("machine_id"),
                machines,
            )[0]
            if mach_id is None:
                mach_id = pick_default_machine_for_non_hair(svc_id or 0, machines)
            if mach_id is None:
                missing.append("machine_id")
                mach_miss = "machine_id"
        else:
            mach_id = resolve_machine_id(
                intent.get("machine_name"),
                intent.get("machine_id"),
                machines,
            )[0]

        if svc_id == TATTOO_SERVICE_ID and not str(intent.get("body_part") or "").strip():
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

        bp_miss: Optional[str] = None
        if svc_id is not None:
            explicit = intent.get("body_part_ids")
            if isinstance(explicit, list) and explicit:
                body_ids, bp_miss = await resolve_body_part_ids(
                    svc_id, intent.get("body_part"), explicit, mach_id
                )
            else:
                body_ids, bp_miss = await resolve_body_part_ids(
                    svc_id, intent.get("body_part"), None, mach_id
                )
            if bp_miss:
                missing.append(bp_miss)
    else:
        # Executor-only: AI must supply CRM IDs from get_* tools — no server-side name→id mapping.
        svc_id = _coerce_int_id(intent.get("service_id"))
        if svc_id is None:
            missing.append("service_id")
        allowed_sids = {_coerce_int_id(s.get("id")) for s in services}
        allowed_sids.discard(None)
        if svc_id is not None and svc_id not in allowed_sids:
            conflicts["service_id"] = {
                "detail": "service_id not found in live CRM services list; call get_services and resend.",
                "service_id": svc_id,
            }

        br_id = _coerce_int_id(intent.get("branch_id"))
        if br_id is None:
            missing.append("branch_id")
        allowed_bids = {_coerce_int_id(b.get("id")) for b in branches}
        allowed_bids.discard(None)
        if br_id is not None and br_id not in allowed_bids:
            conflicts["branch_id"] = {
                "detail": "branch_id not found in live CRM branch list; call get_branches and resend.",
                "branch_id": br_id,
            }

        mach_id = _coerce_int_id(intent.get("machine_id"))
        machine_required = _service_requires_machine(svc_id)
        if svc_id is not None:
            if machine_required and svc_id in LASER_HAIR_REMOVAL_SERVICE_IDS:
                if mach_id is None:
                    missing.append("machine_id")
                elif mach_id not in HAIR_REMOVAL_MACHINE_IDS:
                    conflicts["machine_service"] = {
                        "detail": "machine_id must be a hair-removal device from get_machines for this service.",
                        "machine_id": mach_id,
                        "allowed_machine_ids": sorted(HAIR_REMOVAL_MACHINE_IDS),
                    }
            elif machine_required and svc_id == TATTOO_SERVICE_ID:
                if mach_id is None:
                    missing.append("machine_id")
            elif machine_required:
                if mach_id is None:
                    missing.append("machine_id")

        ex_bp = intent.get("body_part_ids")
        if isinstance(ex_bp, list):
            for x in ex_bp:
                i = _coerce_int_id(x)
                if i is not None and i > 0:
                    body_ids.append(i)
        if svc_id is not None and svc_id in DEFAULT_BODY_PART_REQUIRED_SERVICE_IDS and not body_ids:
            missing.append("body_part_ids")

    dt_local, dt_missing, ambiguities, dt_resolution = _build_api_datetime(intent)
    for m in dt_missing:
        if m not in missing:
            missing.append(m)

    _require_resolved_dt = bool(getattr(config, "BOOKING_REQUIRE_RESOLVED_DATETIME", False)) or not backend_resolves
    if execute and _require_resolved_dt and dt_resolution == "legacy_raw" and dt_local is not None:
        missing.append("resolved_datetime")
        ambiguities.append("booking_requires_explicit_date_and_time_not_raw_nl_only")

    if intent.get("needs_clarification"):
        ambiguities.extend([str(x) for x in (intent.get("ambiguities") or [])])

    invalid: Dict[str, Any] = {}

    if svc_id in LASER_HAIR_REMOVAL_SERVICE_IDS and mach_id is not None:
        if mach_id not in HAIR_REMOVAL_MACHINE_IDS and "machine_service" not in conflicts:
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
        "machine_required": machine_required,
        "body_part_ids": body_ids,
        "timezone": BOOKING_TIMEZONE_LABEL,
        "datetime_resolution_source": dt_resolution,
    }
    if dt_local is not None:
        norm_vals["api_date"] = dt_local.astimezone(BOT_FIXED_TZ).strftime("%Y-%m-%d %H:%M:%S")

    if missing or conflicts:
        hr_booking = "Resolve missing or conflicting fields before booking."
        if "resolved_datetime" in missing:
            hr_booking = (
                "Booking execution requires absolute resolved date and time in Asia/Beirut "
                "(use date YYYY-MM-DD plus time HH:MM, or full datetime in date, or date_components). "
                "Do not rely on raw_user_date_text/raw_user_time_text alone as the execution source of truth."
            )
        elif not backend_resolves and (
            "service_id" in missing
            or "branch_id" in missing
            or "machine_id" in missing
            or "body_part_ids" in missing
        ):
            hr_booking = (
                "Executor mode: the model must call get_services, get_branches, get_machines, and get_body_parts first, "
                "then submit_booking_intent with service_id, branch_id, machine_id (when required), body_part_ids, "
                "and resolved date/time — not names-only or raw NL alone."
            )
        mf_sorted = sorted(set(missing))
        primary = _infer_primary_failure_stage(
            missing=mf_sorted,
            conflicts=conflicts,
            invalid=invalid,
            backend_resolves=backend_resolves,
        )
        issue_keys = list(mf_sorted) + list((conflicts or {}).keys())
        trace_detail = hr_booking
        if issue_keys:
            trace_detail = f"{hr_booking} Issues: {issue_keys}."
        act_trace = _build_booking_activity_trace(
            failure_stage=primary,
            execution_phase="pre_execution",
            backend_resolves_names=backend_resolves,
            intent=intent,
            detail=trace_detail,
            missing_fields=mf_sorted,
            conflicting_fields=conflicts,
            invalid_fields=invalid,
            ambiguities=list(ambiguities) if ambiguities else None,
            datetime_resolution_source=dt_resolution,
            normalized_values_snapshot=norm_vals,
            pipeline_phase="submit_booking_intent",
        )
        act_trace["issue_keys"] = issue_keys
        err = validation_error_response(
            missing_fields=mf_sorted,
            invalid_fields=invalid,
            conflicting_fields=conflicts,
            allowed_values={
                "branches": [{"id": b.get("id"), "name": b.get("name")} for b in branches[:20]],
                "services": [{"id": s.get("id"), "name": s.get("name")} for s in services[:40]],
                "machines": [{"id": m.get("id"), "name": m.get("name")} for m in machines[:40]],
            },
            normalized_values=norm_vals,
            human_readable_reason=hr_booking,
            activity_trace=act_trace,
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

    assert svc_id is not None and br_id is not None and dt_local is not None

    if svc_id in DEFAULT_BODY_PART_REQUIRED_SERVICE_IDS and not body_ids:
        err = validation_error_response(
            missing_fields=["body_part"],
            normalized_values=norm_vals,
            human_readable_reason="body_part_ids required for this service.",
            activity_trace=_build_booking_activity_trace(
                failure_stage="body_part_lookup",
                execution_phase="pre_execution",
                backend_resolves_names=backend_resolves,
                intent=intent,
                detail="Service requires body areas but body_part_ids is empty after validation.",
                missing_fields=["body_part", "body_part_ids"],
                normalized_values_snapshot=norm_vals,
                pipeline_phase="submit_booking_intent",
            ),
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
                activity_trace=_build_booking_activity_trace(
                    failure_stage="backend_validation",
                    execution_phase="pre_execution",
                    backend_resolves_names=backend_resolves,
                    intent=intent,
                    detail=(
                        "Slot rules rejected this datetime: "
                        f"code={sv.get('code')!r}, {sv.get('explanation_en', '')}"
                    ),
                    invalid_fields={"slot": sv.get("code")},
                    normalized_values_snapshot=norm_vals,
                    pipeline_phase="submit_booking_intent",
                    slot_validation=sv,
                ),
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
        ce = cust_err or "Could not ensure customer record."
        err = validation_error_response(
            missing_fields=["customer_name"] if "name" in (cust_err or "") else [],
            human_readable_reason=ce,
            normalized_values=norm_vals,
            activity_trace=_build_booking_activity_trace(
                failure_stage="customer_record",
                execution_phase="pre_execution",
                backend_resolves_names=backend_resolves,
                intent=intent,
                detail=f"Customer ensure failed before CRM: {ce}",
                missing_fields=["customer_name"] if "name" in (cust_err or "") else [],
                normalized_values_snapshot=norm_vals,
                pipeline_phase="submit_booking_intent",
                customer_error=ce,
            ),
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
        shell["activity_trace"] = {
            "pipeline_phase": "submit_booking_intent",
            "failure_stage": None,
            "stage": "booking_tool_execution",
            "execution_phase": "pre_execution",
            "execution_blocked": True,
            "blocked_reason": "execute_booking_false",
            "detail": "Validation passed; CRM create was not invoked because execute_booking=false.",
            "pre_execution": True,
            "during_execution": False,
            "normalized_values_snapshot": norm_vals,
            "payload_ready_preview": {
                "phone": phone_clean,
                "service_id": svc_id,
                "branch_id": br_id,
                "machine_id": mach_id,
                "api_date": norm_vals.get("api_date"),
                "body_part_ids": body_ids,
            },
            "ai_intent_summary": _ai_intent_summary(intent),
        }
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
