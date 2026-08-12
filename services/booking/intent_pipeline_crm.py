"""CRM finalize / legacy create / ensure-customer for booking pipeline (LOC split)."""

from __future__ import annotations

import copy
import os
from typing import Any

import config
from services import api_integrations
from services.booking.constants import (
    BOOKING_TIMEZONE_LABEL,
    HAIR_REMOVAL_MACHINE_IDS,
    _service_requires_machine,
)
from services.booking.intent_pipeline_helpers import (
    _build_booking_activity_trace,
    _coerce_int_id,
    _crm_rejection_validation_error,
    _infer_primary_failure_stage,
    _log_booking_attempt,
    _merge_intent,
)
from services.booking.schemas import validation_error_response


async def finalize_crm_booking_tool_output(
    *,
    user_id: str,
    raw_user_message: str,
    ai_extracted: dict[str, Any],
    norm_vals: dict[str, Any],
    payload: dict[str, Any],
    phase: str,
) -> dict[str, Any]:
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
    function_args: dict[str, Any],
    current_gender: str,
    user_input: str,
) -> dict[str, Any]:
    """
    Internal/legacy path: after chat_response_service preprocessing, run the same CRM create + response
    shape as submit_booking_intent (success + api_response wrapper, or validation_error on CRM reject).
    """
    from services.product_features import boc_booking_enabled, boc_disabled_response

    if not boc_booking_enabled():
        return boc_disabled_response(operation="create_appointment")

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
    body_ids: list[int] = []
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

    norm_vals: dict[str, Any] = {
        "service_id": sid,
        "branch_id": bid,
        "machine_id": mid,
        "body_part_ids": body_ids,
        "timezone": BOOKING_TIMEZONE_LABEL,
        "api_date": date_str,
    }

    missing: list[str] = []
    machine_required_legacy = _service_requires_machine(sid)
    if not machine_required_legacy:
        mid = None
        norm_vals["machine_id"] = None
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
    conflicts: dict[str, Any] = {}
    if machine_required_legacy and mid is not None and mid not in HAIR_REMOVAL_MACHINE_IDS:
        conflicts["machine_service"] = {
            "detail": "machine_id is not an available hair-removal device. Trio is no longer available.",
            "machine_id": mid,
            "allowed_machine_ids": sorted(HAIR_REMOVAL_MACHINE_IDS),
        }
    if missing or conflicts:
        st = config.user_booking_state[user_id]
        st["booking_flow_state"] = "validation_failed"
        intent_snap = _merge_intent(fa)
        mf = sorted(set(missing))
        primary = _infer_primary_failure_stage(
            missing=mf,
            conflicts=conflicts,
            invalid={},
            backend_resolves=False,
        )
        err = validation_error_response(
            missing_fields=mf,
            conflicting_fields=conflicts,
            normalized_values=norm_vals,
            human_readable_reason="Incomplete or invalid arguments for create_appointment; gather valid fields and prefer submit_booking_intent.",
            activity_trace=_build_booking_activity_trace(
                failure_stage=primary,
                execution_phase="pre_execution",
                backend_resolves_names=False,
                intent=intent_snap,
                detail=f"Legacy create_appointment blocked before CRM: missing={mf}, conflicts={list(conflicts.keys())}.",
                missing_fields=mf,
                conflicting_fields=conflicts,
                normalized_values_snapshot=norm_vals,
                pipeline_phase="legacy_create_appointment_validation",
            ),
        )
        st["last_validation_error"] = err
        return err

    payload: dict[str, Any] = {
        "phone": phone,
        "service_id": int(sid or 0),
        "branch_id": int(bid or 0),
        "date": date_str,
    }
    if machine_required_legacy and mid is not None:
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
    customer_name: str | None,
    gender_capitalized: str,
) -> tuple[bool, str | None]:
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
