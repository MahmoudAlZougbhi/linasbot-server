"""Appointment pause/resume/status and customer lookup API (LOC split)."""

from __future__ import annotations

from typing import Any

from services.api_integrations_http import (
    _make_api_request,
    _post_update_status_logged,
    _update_status_post_url_candidates,
    log_report_event,
)


def _phone_clean_for_appointment_api(phone: str) -> str:
    phone_clean = str(phone).replace("+", "").replace(" ", "").replace("-", "")
    if phone_clean.startswith("961"):
        phone_clean = phone_clean[3:]
    return phone_clean


async def pause_appointment(phone: str, appointment_id: int) -> Any:
    """Pauses an appointment by updating its status to Paused."""
    phone_clean = _phone_clean_for_appointment_api(phone)
    print(f"API Call: pause_appointment for phone=***{str(phone_clean)[-4:] if phone_clean else ''}, appointment_id={appointment_id}")
    json_data = {"phone": phone_clean, "appointment_id": appointment_id}
    response = await _make_api_request("POST", "appointments/pause", json_data=json_data)
    if response.get("success"):
        log_report_event(
            "api_call",
            "System",
            "N/A",
            {"api": "pause_appointment", "status": "success", "appointment_id": appointment_id},
        )
    else:
        log_report_event(
            "api_call",
            "System",
            "N/A",
            {
                "api": "pause_appointment",
                "status": "failed",
                "error": response.get("message"),
                "appointment_id": appointment_id,
            },
        )
    return response


async def update_appointments_status(
    appointment_ids: list[int],
    status_id: int,
    date: str | None = None,
) -> Any:
    """
    CRM: POST appointment status on host ``/api/...`` (not under ``/agent/``).
    Tries ``/api/appointments/update/status`` then ``/api/appointments/update-status`` unless
    ``LINASLASER_UPDATE_STATUS_PATH`` is set.

    Body:
    - appointment_ids: required array of integers (canonical)
    - appointment_id: same ids as an array (some CRM stacks expect this singular key with an array value, e.g. ``[35306]``)
    - status_id: required
    - date: **only** when status_id == 3 (Postponed); omitted for all other statuses (including 2 Available)
    """
    ids: list[int] = []
    for raw in appointment_ids or []:
        try:
            ids.append(int(raw))
        except (TypeError, ValueError):
            continue
    if not ids:
        return {"success": False, "message": "invalid_appointment_ids"}
    try:
        status_id_int = int(status_id)
    except (TypeError, ValueError):
        return {"success": False, "message": "invalid_status_id"}

    ids_list = list(ids)
    json_data: dict[str, Any] = {
        "appointment_ids": ids_list,
        "appointment_id": ids_list,
        "status_id": status_id_int,
    }
    if status_id_int == 3:
        date_str = str(date or "").strip()
        if not date_str:
            return {"success": False, "message": "date_required_for_postponed_status"}
        json_data["date"] = date_str

    print(
        "API Call: update_appointments_status "
        f"appointment_ids={ids}, status_id={status_id_int}, "
        f"date={'(omitted)' if status_id_int != 3 else json_data.get('date')}"
    )
    path_candidates = _update_status_post_url_candidates()
    response: dict = {"success": False, "message": "update_status_endpoint_not_tried"}
    path_used = path_candidates[0] if path_candidates else ""
    attempted_paths: list[str] = []
    path_errors: list[dict] = []
    for path in path_candidates:
        if not path:
            continue
        path_used = path
        attempted_paths.append(path)
        response = await _post_update_status_logged(path, json_data)
        if response.get("success"):
            break
        msg = str(response.get("message") or "").lower()
        path_errors.append(
            {
                "path": path,
                "status_code": response.get("status_code"),
                "message": response.get("message"),
            }
        )
        code = response.get("status_code")
        if code in (404, 405) or "not found" in msg:
            print(f"API Call: update_appointments_status — {path} HTTP {code!r}, trying next path")
            continue
        break
    if isinstance(response, dict):
        response = dict(response)
        response["path"] = path_used
        response["attempted_paths"] = attempted_paths
        if path_errors:
            response["path_errors"] = path_errors
    if response.get("success"):
        log_report_event(
            "api_call",
            "System",
            "N/A",
            {
                "api": "update_appointments_status",
                "status": "success",
                "appointment_ids": ids,
                "status_id": status_id_int,
                "date": json_data.get("date") if status_id_int == 3 else None,
                "path": path_used,
                "final_url": response.get("final_url"),
            },
        )
    else:
        log_report_event(
            "api_call",
            "System",
            "N/A",
            {
                "api": "update_appointments_status",
                "status": "failed",
                "error": response.get("message"),
                "appointment_ids": ids,
                "status_id": status_id_int,
                "date": json_data.get("date") if status_id_int == 3 else None,
                "path": path_used,
                "final_url": response.get("final_url"),
            },
        )
    return response


async def resume_appointment(phone: str, appointment_id: int, endpoint: str | None = None) -> Any:
    """
    Paused → Available: POST CRM update-status with body
    ``{"appointment_ids": [id], "appointment_id": [id], "status_id": 2}`` only (no ``date``).

    ``phone`` and ``endpoint`` are kept for tool/signature compatibility; CRM update-status does not
    use them. Override URLs via ``LINASLASER_UPDATE_STATUS_PATH`` (see ``update_appointments_status``).
    """
    _ = _phone_clean_for_appointment_api(phone)
    _ = endpoint
    response = await update_appointments_status([int(appointment_id)], status_id=2)
    merged = dict(response) if isinstance(response, dict) else {"success": False, "message": str(response)}
    merged["path"] = merged.get("path") or merged.get("final_url") or "api/appointments/update-status"
    if merged.get("success"):
        log_report_event(
            "api_call",
            "System",
            "N/A",
            {
                "api": "resume_appointment",
                "status": "success",
                "appointment_id": appointment_id,
                "path": merged["path"],
            },
        )
    else:
        log_report_event(
            "api_call",
            "System",
            "N/A",
            {
                "api": "resume_appointment",
                "status": "failed",
                "error": merged.get("message"),
                "appointment_id": appointment_id,
                "path": merged["path"],
            },
        )
    return merged


async def get_clients_without_today(date: str | None = None, branch_id: int | None = None) -> Any:
    """Returns all active clients who do not have appointments on the given date."""
    print(f"API Call: get_clients_without_today for date={date}, branch_id={branch_id}")
    params: dict[str, Any] = {}
    if date:
        params["date"] = date
    if branch_id is not None:
        params["branch_id"] = branch_id
    response = await _make_api_request("GET", "appointments/clients/without-today", params=params)
    if response.get("success"):
        log_report_event(
            "api_call", "System", "N/A", {"api": "get_clients_without_today", "status": "success", "date": date}
        )
    else:
        log_report_event(
            "api_call",
            "System",
            "N/A",
            {"api": "get_clients_without_today", "status": "failed", "error": response.get("message")},
        )
    return response


async def get_customer_sessions(customer_id: int) -> Any:
    """Returns sessions (appointments) for a customer including service, area, status, and notes."""
    print(f"API Call: get_customer_sessions for customer_id={customer_id}")
    params = {"customer_id": customer_id}
    response = await _make_api_request("GET", "customers/sessions", params=params)
    if response.get("success"):
        log_report_event(
            "api_call",
            "System",
            "N/A",
            {"api": "get_customer_sessions", "status": "success", "customer_id": customer_id},
        )
    else:
        log_report_event(
            "api_call",
            "System",
            "N/A",
            {
                "api": "get_customer_sessions",
                "status": "failed",
                "error": response.get("message"),
                "customer_id": customer_id,
            },
        )
    return response


async def add_customer_note(phone: str, note: str) -> Any:
    """Adds a note to the customer record by phone number."""
    phone_clean = str(phone).replace("+", "").replace(" ", "").replace("-", "")
    if phone_clean.startswith("961"):
        phone_clean = phone_clean[3:]
    print(f"API Call: add_customer_note for phone=***{str(phone_clean)[-4:] if phone_clean else ''}")
    json_data = {"phone": phone_clean, "note": note[:1000]}
    response = await _make_api_request("POST", "customers/notes/add", json_data=json_data)
    if response.get("success"):
        log_report_event(
            "api_call", "System", "N/A", {"api": "add_customer_note", "status": "success", "phone": phone_clean}
        )
    else:
        log_report_event(
            "api_call",
            "System",
            "N/A",
            {"api": "add_customer_note", "status": "failed", "error": response.get("message"), "phone": phone_clean},
        )
    return response


async def get_all_customers(date: str | None = None, from_date: str | None = None, to_date: str | None = None) -> Any:
    """Returns all customers. Can filter by date, from_date, or to_date (creation date)."""
    print(f"API Call: get_all_customers date={date} from={from_date} to={to_date}")
    params = {}
    if date:
        params["date"] = date
    if from_date:
        params["from"] = from_date
    if to_date:
        params["to"] = to_date
    response = await _make_api_request("GET", "customers/all", params=params)
    if response.get("success"):
        log_report_event(
            "api_call",
            "System",
            "N/A",
            {"api": "get_all_customers", "status": "success", "count": len(response.get("data", []))},
        )
    else:
        log_report_event(
            "api_call",
            "System",
            "N/A",
            {"api": "get_all_customers", "status": "failed", "error": response.get("message")},
        )
    return response


async def get_customer_by_phone(phone: str) -> Any:
    """Retrieves customer details by phone number. Accepts any format; normalizes to E.164 then API local format."""
    from utils.phone_utils import normalize_phone

    normalized = normalize_phone(phone)
    if normalized and normalized.startswith("+961"):
        phone_clean = normalized[4:]  # strip "+961"
    else:
        phone_clean = str(phone).replace("+", "").replace(" ", "").replace("-", "")
        if phone_clean.startswith("961"):
            phone_clean = phone_clean[3:]
    print(f"API Call: get_customer_by_phone for phone=***{str(phone_clean)[-4:] if phone_clean else ''}")
    params = {"phone": phone_clean}
    response = await _make_api_request("GET", "customers/by-phone", params=params)  # Assuming this endpoint exists
    if response.get("success"):
        log_report_event(
            "api_call",
            "System",
            "N/A",
            {
                "api": "get_customer_by_phone",
                "status": "success",
                "phone": phone_clean,
                "customer": response.get("data"),
            },
        )
    else:
        log_report_event(
            "api_call",
            "System",
            "N/A",
            {
                "api": "get_customer_by_phone",
                "status": "failed",
                "error": response.get("message"),
                "phone": phone_clean,
            },
        )
    return response


async def get_customer_appointments(phone: str) -> Any:
    """Retrieves all appointments for a customer by phone number (no country code)."""
    print(f"API Call: get_customer_appointments for phone=***{str(phone)[-4:] if phone else ''}")

    # Remove country code if present (e.g., +961 -> empty, keep only digits)
    phone_clean = phone.replace("+", "").replace(" ", "")
    if phone_clean.startswith("961"):
        phone_clean = phone_clean[3:]  # Remove Lebanon country code

    params = {"phone": phone_clean}
    response = await _make_api_request("GET", "appointments/customer", params=params)

    if response.get("success"):
        log_report_event(
            "api_call", "System", "N/A", {"api": "get_customer_appointments", "status": "success", "phone": phone_clean}
        )
    else:
        log_report_event(
            "api_call",
            "System",
            "N/A",
            {
                "api": "get_customer_appointments",
                "status": "failed",
                "error": response.get("message"),
                "phone": phone_clean,
            },
        )

    return response

