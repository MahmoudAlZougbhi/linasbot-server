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
from typing import Any

import config
from services.booking.constants import (
    BOOKING_TIMEZONE_LABEL,
    DEFAULT_BODY_PART_REQUIRED_SERVICE_IDS,
    _service_requires_machine,  # noqa: F401 — public re-export for tests/callers
)
from services.booking.intent_pipeline_crm import (  # noqa: F401
    _ensure_customer,
    finalize_crm_booking_tool_output,
    legacy_create_appointment_tool_output,
)
from services.booking.intent_pipeline_helpers import (  # noqa: F401
    _ai_intent_summary,
    _build_api_datetime,
    _build_booking_activity_trace,
    _coerce_int_id,
    _crm_rejection_validation_error,
    _effective_gender,
    _infer_primary_failure_stage,
    _log_booking_attempt,
    _merge_body_parts_sessions_from_intent,
    _merge_intent,
)
from services.booking.intent_pipeline_resolve import resolve_submit_booking_entities
from services.booking.schemas import (  # noqa: F401 — empty_booking_intent_template re-exported
    empty_booking_intent_template,
    success_validation_shell,
    validation_error_response,
)
from utils.appointment_slot_rules import parse_normalized_api_datetime, validate_booking_slot
from utils.datetime_utils import BOT_FIXED_TZ


async def handle_submit_booking_intent(
    *,
    user_id: str,
    phone: str,
    current_gender: str,
    user_input: str,
    function_args: dict[str, Any],
) -> dict[str, Any]:
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

    resolved = await resolve_submit_booking_entities(
        intent=intent,
        raw_msg=raw_msg,
        user_input=user_input,
        gender_raw=gender_raw,
        backend_resolves=backend_resolves,
        execute=execute,
    )
    intent = resolved.intent
    services = resolved.services
    branches = resolved.branches
    machines = resolved.machines
    missing = resolved.missing
    conflicts = resolved.conflicts
    ambiguities = resolved.ambiguities
    invalid = resolved.invalid
    svc_id = resolved.svc_id
    br_id = resolved.br_id
    mach_id = resolved.mach_id
    body_ids = resolved.body_ids
    machine_required = resolved.machine_required
    dt_local = resolved.dt_local
    dt_resolution = resolved.dt_resolution
    norm_vals = resolved.norm_vals

    if missing or conflicts:
        hr_booking = "Resolve missing or conflicting fields before booking."
        if "resolved_datetime" in missing:
            hr_booking = (
                "Booking execution requires absolute resolved date and time in Asia/Beirut "
                "(use date YYYY-MM-DD plus time HH:MM, or full datetime in date, or date_components). "
                "Do not rely on raw_user_date_text/raw_user_time_text alone as the execution source of truth."
            )
        elif not backend_resolves and (
            "service_id" in missing or "branch_id" in missing or "machine_id" in missing or "body_part_ids" in missing
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
                        f"Slot rules rejected this datetime: code={sv.get('code')!r}, {sv.get('explanation_en', '')}"
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

    payload_bps = _merge_body_parts_sessions_from_intent(body_ids, intent.get("body_parts_with_sessions"))
    payload: dict[str, Any] = {
        "phone": phone_clean,
        "service_id": svc_id,
        "branch_id": br_id,
        "date": api_date,
        "body_part_ids": body_ids,
        "body_parts_with_sessions": payload_bps,
    }
    if machine_required and mach_id is not None:
        payload["machine_id"] = mach_id
    return await finalize_crm_booking_tool_output(
        user_id=user_id,
        raw_user_message=raw_msg,
        ai_extracted=intent,
        norm_vals=norm_vals,
        payload=payload,
        phase="submit_booking_intent_execute",
    )
