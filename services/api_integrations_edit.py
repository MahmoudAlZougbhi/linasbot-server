"""Appointment edit and paused-update API (LOC split)."""

from __future__ import annotations

import os
from typing import Any

from services.api_integrations_booking import (
    _body_part_session_row,
    _clean_body_part_ids_for_api,
    _clean_body_parts_with_sessions_for_api,
)
from services.api_integrations_http import _make_api_request, log_report_event
from services.api_integrations_status import _phone_clean_for_appointment_api

async def edit_appointment(
    appointment_id: int,
    phone: str | None = None,
    user_code: str | None = None,
    service_id: int | None = None,
    machine_id: int | None = None,
    branch_id: int | None = None,
    date: str | None = None,
    body_part_ids: list | None = None,
    body_parts_with_sessions: list | None = None,
    session_number: int | None = None,
    discount_percentage: float | None = None,
    discount_amount: float | None = None,
    total_cost_after_discount: float | None = None,
    hidden: bool | None = None,
    **kwargs: Any,
) -> Any:
    """
    POST appointments/edit — full appointment update (BOC doc).
    Either phone OR user_code required. Prefer body_parts OR root session_number, not both unnecessarily.
    Path: LINASLASER_APPOINTMENTS_EDIT_PATH (default appointments/edit).
    """
    path = (os.getenv("LINASLASER_APPOINTMENTS_EDIT_PATH") or "appointments/edit").strip().lstrip("/")
    ph = str(phone or "").strip()
    uc = str(user_code or "").strip()
    if not ph and not uc:
        return {
            "success": False,
            "message": "edit_appointment requires phone or user_code (per API doc).",
        }

    json_data: dict = {"appointment_id": int(appointment_id)}
    if ph:
        json_data["phone"] = _phone_clean_for_appointment_api(ph)
    if uc:
        json_data["user_code"] = uc
    if service_id is not None:
        try:
            json_data["service_id"] = int(service_id)
        except (TypeError, ValueError):
            pass
    if machine_id is not None:
        try:
            json_data["machine_id"] = int(machine_id)
        except (TypeError, ValueError):
            pass
    if branch_id is not None:
        try:
            json_data["branch_id"] = int(branch_id)
        except (TypeError, ValueError):
            pass
    if date is not None and str(date).strip():
        json_data["date"] = str(date).strip()

    cleaned_bps = _clean_body_parts_with_sessions_for_api(body_parts_with_sessions)
    if not cleaned_bps and body_part_ids:
        sn0 = 1
        if session_number is not None:
            try:
                sn0 = int(session_number)
            except (TypeError, ValueError):
                sn0 = 1
            if sn0 < 1:
                sn0 = 1
        cleaned_bps = [_body_part_session_row(bid, sn0) for bid in _clean_body_part_ids_for_api(body_part_ids)]

    if cleaned_bps:
        json_data["body_parts"] = cleaned_bps
    elif session_number is not None:
        try:
            sn = int(session_number)
            if sn >= 1:
                json_data["session_number"] = sn
        except (TypeError, ValueError):
            pass

    if discount_percentage is not None:
        try:
            json_data["discount_percentage"] = float(discount_percentage)
        except (TypeError, ValueError):
            pass
    if discount_amount is not None:
        try:
            json_data["discount_amount"] = float(discount_amount)
        except (TypeError, ValueError):
            pass
    if total_cost_after_discount is not None:
        try:
            json_data["total_cost_after_discount"] = float(total_cost_after_discount)
        except (TypeError, ValueError):
            pass
    if hidden is not None:
        json_data["hidden"] = bool(hidden)

    print(f"API Call: edit_appointment path={path} appointment_id={appointment_id} keys={list(json_data.keys())}")
    response = await _make_api_request("POST", path, json_data=json_data)
    if response.get("success"):
        log_report_event(
            "api_call",
            "System",
            "N/A",
            {"api": "edit_appointment", "status": "success", "appointment_id": appointment_id, "path": path},
        )
    else:
        log_report_event(
            "api_call",
            "System",
            "N/A",
            {
                "api": "edit_appointment",
                "status": "failed",
                "error": response.get("message"),
                "appointment_id": appointment_id,
                "path": path,
            },
        )
    return response


async def update_paused_appointment(
    appointment_id: int,
    phone: str,
    date: str | None = None,
    machine_id: int | None = None,
    body_part_ids: list | None = None,
    body_parts_with_sessions: list | None = None,
    status: str | None = None,
    user_code: str | None = None,
) -> Any:
    """
    Updates paused appointment details (date, machine, body parts, sessions, status).
    Intended for paused-row editing workflows where the AI prepares a full JSON patch.
    """
    phone_clean = _phone_clean_for_appointment_api(phone)
    path = (os.getenv("LINASLASER_UPDATE_PAUSED_APPOINTMENT_PATH") or "appointments/edit").strip().lstrip("/")
    print(f"API Call: update_paused_appointment appointment_id={appointment_id}, phone={phone_clean}, path={path}")

    json_data: dict = {
        "appointment_id": int(appointment_id),
        "phone": phone_clean,
    }
    if date is not None and str(date).strip():
        json_data["date"] = str(date).strip()
    if machine_id is not None:
        try:
            json_data["machine_id"] = int(machine_id)
        except (TypeError, ValueError):
            pass
    clean_ids = _clean_body_part_ids_for_api(body_part_ids or [])
    cleaned_sessions = _clean_body_parts_with_sessions_for_api(body_parts_with_sessions)
    if clean_ids:
        json_data["body_part_ids"] = clean_ids
    if cleaned_sessions:
        json_data["body_parts"] = cleaned_sessions
    elif clean_ids:
        json_data["body_parts"] = [_body_part_session_row(bid, 1) for bid in clean_ids]

    status_raw = (status or "").strip()
    default_set_available = os.getenv("LINASLASER_UPDATE_PAUSED_DEFAULT_STATUS_AVAILABLE", "true").lower() in (
        "1",
        "true",
        "yes",
    )
    if status_raw:
        json_data["status"] = status_raw
    elif default_set_available:
        json_data["status"] = "Available"
    if user_code:
        json_data["user_code"] = user_code

    response = await _make_api_request("POST", path, json_data=json_data)
    if response.get("success"):
        log_report_event(
            "api_call",
            "System",
            "N/A",
            {
                "api": "update_paused_appointment",
                "status": "success",
                "appointment_id": appointment_id,
                "path": path,
            },
        )
        # If edit sets Available, also POST update-status so CRM row leaves Paused when needed.
        target_available = str(json_data.get("status") or "").strip().lower() in (
            "available",
            "active",
            "resume",
            "resumed",
        )
        if target_available:
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
                "api": "update_paused_appointment",
                "status": "failed",
                "error": response.get("message"),
                "appointment_id": appointment_id,
                "path": path,
            },
        )
    return response

