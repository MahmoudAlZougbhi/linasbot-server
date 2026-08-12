"""Booking intent pipeline helpers (LOC split)."""

from __future__ import annotations

import datetime
import json
import re
from typing import Any

import config
from services.booking.schemas import empty_booking_intent_template, validation_error_response
from utils.datetime_utils import (
    align_datetime_to_day_reference,
    datetime_from_ai_date_components,
    now_in_bot_tz,
    parse_datetime_flexible,
)


def _log_booking_attempt(payload: dict[str, Any]) -> None:
    try:
        line = json.dumps(payload, default=str, ensure_ascii=False)
    except (TypeError, ValueError):
        line = str(payload)
    print(f"[BOOKING_PIPELINE] {line[:12000]}")


def _ai_intent_summary(intent: dict[str, Any]) -> dict[str, Any]:
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
    missing: list[str],
    conflicts: dict[str, Any],
    invalid: dict[str, Any],
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
    intent: dict[str, Any],
    detail: str = "",
    missing_fields: list[str] | None = None,
    conflicting_fields: dict[str, Any] | None = None,
    invalid_fields: dict[str, Any] | None = None,
    ambiguities: list[str] | None = None,
    datetime_resolution_source: str | None = None,
    normalized_values_snapshot: dict[str, Any] | None = None,
    pipeline_phase: str = "submit_booking_intent",
    slot_validation: dict[str, Any] | None = None,
    customer_error: str | None = None,
) -> dict[str, Any]:
    """
    Structured observability for activity flow: stage, pre/post execution, inputs, missing IDs.
    execution_phase: pre_execution | during_execution
    """
    pre_exec = execution_phase == "pre_execution"
    trace: dict[str, Any] = {
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


def _merge_intent(function_args: dict[str, Any]) -> dict[str, Any]:
    base = empty_booking_intent_template()
    fa = dict(function_args or {})
    for k in list(base.keys()):
        if fa.get(k) is not None:
            base[k] = fa[k]
    return base


def _effective_gender(intent: dict[str, Any], current_gender: str) -> str:
    g = intent.get("gender") or current_gender
    return (g or "unknown").strip().lower()


_DATE_ONLY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _build_api_datetime(
    intent: dict[str, Any],
) -> tuple[datetime.datetime | None, list[str], list[str], str]:
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
    missing: list[str] = []
    amb: list[str] = []
    now = now_in_bot_tz()
    dt: datetime.datetime | None = None
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


def _coerce_int_id(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _merge_body_parts_sessions_from_intent(
    body_ids: list[int],
    raw_bps: Any,
) -> list[dict[str, int]]:
    """
    Build BOC body_parts list: use model-provided session_number per body_part_id when valid;
    fill missing ids with session_number=1. Order follows body_ids.
    """
    if not body_ids:
        return []
    allowed = {int(b) for b in body_ids}
    by_id: dict[int, int] = {}
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
    out: list[dict[str, int]] = []
    for bid in body_ids:
        out.append({"body_part_id": int(bid), "session_number": int(by_id.get(bid, 1))})
    return out




def _crm_rejection_validation_error(
    norm_vals: dict[str, Any],
    api_resp: dict[str, Any],
    *,
    endpoint_payload: dict[str, Any] | None = None,
    pipeline_phase: str = "submit_booking_intent_execute",
    ai_extracted: dict[str, Any] | None = None,
) -> dict[str, Any]:
    api_msg = str(api_resp.get("message") or "").strip()
    inv: dict[str, Any] = {"calendar": "slot_unavailable_or_conflict"}
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
    payload_summary: dict[str, Any] | None = None
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
