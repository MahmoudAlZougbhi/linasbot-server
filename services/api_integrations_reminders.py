"""Appointment reminder and lookup API calls (LOC split)."""

from __future__ import annotations

from typing import Any

from services.api_integrations_http import _make_api_request, log_report_event


async def send_appointment_reminders(
    date: str | None = None, phone: str | None = None, user_code: str | None = None, status: str | None = None
) -> Any:
    """
    Retrieves appointments with optional filters.

    Args:
        date: Filter by date (YYYY-MM-DD)
        phone: Filter by phone number
        user_code: Filter by user code
        status: Filter by status (done, available, postponed, paused)
    """
    print(
        f"API Call: send_appointment_reminders for date={date}, phone=***{str(phone)[-4:] if phone else ''}, user_code={user_code}, status={status}"
    )
    params = {}
    if date:
        params["date"] = date
    if phone:
        params["phone"] = phone
    if user_code:
        params["user_code"] = user_code
    if status:
        params["status"] = status
    response = await _make_api_request("GET", "appointments/reminders", params=params)

    # DEBUG: Log response structure for first call only
    if date == "2026-01-14" and response.get("success"):
        print(f"🔍 DEBUG: API Response Structure for date={date}")
        print(f"   Response keys: {list(response.keys())}")
        if "data" in response:
            data = response["data"]
            print(f"   Data type: {type(data)}")
            if isinstance(data, dict):
                print(f"   Data keys: {list(data.keys())}")
                if "appointments" in data and data["appointments"]:
                    print(
                        f"   First appointment sample: {data['appointments'][0] if data['appointments'] else 'EMPTY'}"
                    )
            elif isinstance(data, list) and data:
                print(f"   First item in data list: {data[0]}")

    if response.get("success"):
        log_report_event(
            "api_call", "System", "N/A", {"api": "send_appointment_reminders", "status": "success", "params": params}
        )
    else:
        log_report_event(
            "api_call",
            "System",
            "N/A",
            {
                "api": "send_appointment_reminders",
                "status": "failed",
                "error": response.get("message"),
                "params": params,
            },
        )
    return response


async def check_next_appointment(phone: str, user_code: str | None = None) -> Any:
    """Returns the next scheduled appointment for a client."""
    # Clean phone number to match API expected format (without + prefix and country code)
    phone_clean = str(phone).replace("+", "").replace(" ", "").replace("-", "")
    if phone_clean.startswith("961"):
        phone_clean = phone_clean[3:]  # Remove Lebanon country code

    print(f"API Call: check_next_appointment for phone=***{str(phone_clean)[-4:] if phone_clean else ''} (original_last4=***{str(phone)[-4:] if phone else ''}), user_code={user_code}")
    params = {"phone": phone_clean}
    if user_code:
        params["user_code"] = user_code
    response = await _make_api_request("GET", "appointments/next", params=params)
    if response.get("success"):
        log_report_event(
            "api_call",
            "System",
            "N/A",
            {"api": "check_next_appointment", "status": "success", "phone": phone, "appointment": response.get("data")},
        )
    else:
        log_report_event(
            "api_call",
            "System",
            "N/A",
            {"api": "check_next_appointment", "status": "failed", "error": response.get("message"), "phone": phone},
        )
    return response


async def get_sessions_count_by_phone(
    phone: str | None = None, user_code: str | None = None, service_ids: list | None = None
) -> Any:
    """Returns the number of sessions a client has attended, based on their phone number or user code."""
    # Clean phone number to match API expected format (without + prefix and country code)
    phone_clean = None
    if phone:
        phone_clean = str(phone).replace("+", "").replace(" ", "").replace("-", "")
        if phone_clean.startswith("961"):
            phone_clean = phone_clean[3:]  # Remove Lebanon country code

    print(
        f"API Call: get_sessions_count_by_phone for phone=***{str(phone_clean)[-4:] if phone_clean else ''} (original_last4=***{str(phone)[-4:] if phone else ''}), user_code={user_code}, service_ids={service_ids}"
    )
    params: dict[str, Any] = {}
    if phone_clean:
        params["phone"] = phone_clean
    if user_code:
        params["user_code"] = user_code
    if service_ids:
        params["service_ids"] = service_ids
    response = await _make_api_request("GET", "appointments/sessions/count", params=params)
    if response.get("success"):
        log_report_event(
            "api_call",
            "System",
            "N/A",
            {"api": "get_sessions_count_by_phone", "status": "success", "phone": phone, "data": response.get("data")},
        )
    else:
        log_report_event(
            "api_call",
            "System",
            "N/A",
            {
                "api": "get_sessions_count_by_phone",
                "status": "failed",
                "error": response.get("message"),
                "phone": phone,
            },
        )
    return response


async def move_client_branch(
    phone: str,
    from_branch_id: int,
    to_branch_id: int,
    new_date: str | None = None,
    user_code: str | None = None,
    response_confirm: str = "yes",
) -> Any:
    """Moves a client's future appointments to a different branch.

    `new_date` is optional: only included in the JSON payload when a non-empty
    string is provided (aligns with Agent API docs where rescheduling to a
    specific day may be optional for a pure branch move).
    """
    # Clean phone number to match API expected format (without + prefix and country code)
    phone_clean = str(phone).replace("+", "").replace(" ", "").replace("-", "")
    if phone_clean.startswith("961"):
        phone_clean = phone_clean[3:]  # Remove Lebanon country code

    nd = (new_date or "").strip() if new_date is not None else ""
    print(
        f"API Call: move_client_branch for phone=***{str(phone_clean)[-4:] if phone_clean else ''} (original_last4=***{str(phone)[-4:] if phone else ''}), "
        f"from={from_branch_id}, to={to_branch_id}, new_date={'set' if nd else 'omitted'}"
    )
    json_data = {
        "phone": phone_clean,
        "from_branch_id": from_branch_id,
        "to_branch_id": to_branch_id,
        "response": response_confirm,
    }
    if nd:
        json_data["new_date"] = nd
    if user_code:
        json_data["user_code"] = user_code
    response = await _make_api_request("POST", "appointments/branch/move", json_data=json_data)
    if response.get("success"):
        log_report_event(
            "api_call",
            "System",
            "N/A",
            {"api": "move_client_branch", "status": "success", "phone": phone, "details": response.get("data")},
        )
    else:
        log_report_event(
            "api_call",
            "System",
            "N/A",
            {"api": "move_client_branch", "status": "failed", "error": response.get("message"), "phone": phone},
        )
    return response


async def check_appointment_payment(phone: str, user_code: str | None = None) -> Any:
    """Checks the payment status of a client's appointments."""
    # Clean phone number to match API expected format (without + prefix and country code)
    phone_clean = str(phone).replace("+", "").replace(" ", "").replace("-", "")
    if phone_clean.startswith("961"):
        phone_clean = phone_clean[3:]  # Remove Lebanon country code

    print(f"API Call: check_appointment_payment for phone=***{str(phone_clean)[-4:] if phone_clean else ''} (original_last4=***{str(phone)[-4:] if phone else ''}), user_code={user_code}")
    params = {"phone": phone_clean}
    if user_code:
        params["user_code"] = user_code
    response = await _make_api_request("GET", "appointments/payment", params=params)
    if response.get("success"):
        log_report_event(
            "api_call",
            "System",
            "N/A",
            {"api": "check_appointment_payment", "status": "success", "phone": phone, "payment": response.get("data")},
        )
    else:
        log_report_event(
            "api_call",
            "System",
            "N/A",
            {"api": "check_appointment_payment", "status": "failed", "error": response.get("message"), "phone": phone},
        )
    return response


async def get_pricing_details(
    service_id: int, machine_id: int | None = None, body_part_ids: list | None = None, branch_id: int | None = None
) -> Any:
    """Returns pricing details for appointments or services based on specified criteria."""
    print(f"API Call: get_pricing_details for service_id={service_id}")
    params: dict[str, Any] = {"service_id": service_id}
    if machine_id:
        params["machine_id"] = machine_id
    # Format body_part_ids as PHP-style array params (body_part_ids[]=1&body_part_ids[]=2)
    if body_part_ids:
        if isinstance(body_part_ids, list):
            params["body_part_ids[]"] = body_part_ids
        else:
            params["body_part_ids[]"] = [body_part_ids]
    if branch_id:
        params["branch_id"] = branch_id
    response = await _make_api_request("GET", "appointments/pricing", params=params)
    if response.get("success"):
        log_report_event(
            "api_call",
            "System",
            "N/A",
            {
                "api": "get_pricing_details",
                "status": "success",
                "service_id": service_id,
                "pricing": response.get("data"),
            },
        )
    else:
        log_report_event(
            "api_call",
            "System",
            "N/A",
            {
                "api": "get_pricing_details",
                "status": "failed",
                "error": response.get("message"),
                "service_id": service_id,
            },
        )
    return response


async def get_missed_appointments(date: str | None = None) -> Any:
    """Returns a list of missed appointments for the clinic."""
    print(f"API Call: get_missed_appointments for date={date}")
    params = {}
    if date:
        params["date"] = date
    response = await _make_api_request("GET", "appointments/missed", params=params)
    if response.get("success"):
        log_report_event(
            "api_call",
            "System",
            "N/A",
            {"api": "get_missed_appointments", "status": "success", "data": response.get("data")},
        )
    else:
        log_report_event(
            "api_call",
            "System",
            "N/A",
            {"api": "get_missed_appointments", "status": "failed", "error": response.get("message"), "date": date},
        )
    return response


async def get_paused_appointments_between_dates(start_date: str, end_date: str, service_id: int | None = None) -> Any:
    """
    Returns a list of paused appointments between two dates.

    Args:
        start_date: Required. Start date in YYYY-MM-DD format (e.g., "2026-01-01")
        end_date: Required. End date in YYYY-MM-DD format (e.g., "2026-02-01")
        service_id: . Filter by service ID

    Returns:
        API response with paused appointments data
    """
    print(
        f"API Call: get_paused_appointments_between_dates for start_date={start_date}, end_date={end_date}, service_id={service_id}"
    )
    params: dict[str, Any] = {"start_date": start_date, "end_date": end_date}
    if service_id is not None:
        params["service_id"] = service_id

    response = await _make_api_request("GET", "appointments/paused/between-dates", params=params)
    if response.get("success"):
        log_report_event(
            "api_call",
            "System",
            "N/A",
            {
                "api": "get_paused_appointments_between_dates",
                "status": "success",
                "start_date": start_date,
                "end_date": end_date,
                "service_id": service_id,
            },
        )
    else:
        log_report_event(
            "api_call",
            "System",
            "N/A",
            {
                "api": "get_paused_appointments_between_dates",
                "status": "failed",
                "error": response.get("message"),
                "start_date": start_date,
                "end_date": end_date,
                "service_id": service_id,
            },
        )
    return response


async def get_appointment_details(appointment_id: int) -> Any:
    """Retrieves detailed information about a specific appointment by ID."""
    print(f"API Call: get_appointment_details for appointment_id={appointment_id}")
    params = {"appointment_id": appointment_id}
    response = await _make_api_request("GET", "appointment", params=params)
    if response.get("success"):
        log_report_event(
            "api_call",
            "System",
            "N/A",
            {"api": "get_appointment_details", "status": "success", "appointment_id": appointment_id},
        )
    else:
        log_report_event(
            "api_call",
            "System",
            "N/A",
            {
                "api": "get_appointment_details",
                "status": "failed",
                "error": response.get("message"),
                "appointment_id": appointment_id,
            },
        )
    return response

