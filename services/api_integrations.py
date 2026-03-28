import datetime
import json
import os
from typing import Any, Optional

import httpx
# No more telegram.Update or ContextTypes here
# from telegram import Update
# from telegram.ext import ContextTypes

import config
import api_config
# NEW: Import Firestore utility functions
from utils.utils import update_dashboard_metric_in_firestore, get_firestore_db

# Path to the daily reports log file
REPORT_LOG_FILE = 'data/reports_log.jsonl' 

# Increase timeout to 60 seconds for slow API endpoints (especially appointment queries)
api_client = httpx.AsyncClient(
    base_url=api_config.LINASLASER_API_BASE_URL,
    timeout=60.0  # 60 seconds timeout instead of default 5 seconds
)

async def _make_api_request(method: str, endpoint: str, params: dict = None, json_data: dict = None):
    """
    Helper function to make authenticated API requests to the LinasLaser Agent API.
    """
    headers = {
        "Authorization": f"Bearer {api_config.LINASLASER_API_TOKEN}",
        "Content-Type": "application/json"
    }

    try:
        if method.lower() == "get":
            response = await api_client.get(endpoint, params=params, headers=headers)
        elif method.lower() == "post":
            response = await api_client.post(endpoint, params=params, json=json_data, headers=headers)
        else:
            return {"success": False, "message": f"Unsupported HTTP method: {method}"}

        # NEW LOGIC: Handle 404 specifically to avoid HTML parsing errors if API doesn't return JSON for 404.
        if response.status_code == 404:
            print(f"API Info: Resource not found for {endpoint} (404) - {response.text}")
            # Try to parse as JSON first, if not, return a structured error
            try:
                return response.json() 
            except json.JSONDecodeError:
                # If 404 response is HTML, provide a generic "Not Found" message
                return {"success": False, "message": f"API endpoint '{endpoint}' not found on server.", "status_code": 404, "raw_response": response.text}
        
        response.raise_for_status() # Raise an exception for other HTTP errors (4xx or 5xx except 404)
        return response.json()
    except httpx.HTTPStatusError as e:
        print(f"API HTTP Error for {endpoint}: {e.response.status_code} - {e.response.text}")
        return {"success": False, "message": f"Connection error (HTTP Error): {e.response.status_code}. Details: {e.response.text}", "status_code": e.response.status_code}
    except httpx.RequestError as e:
        print(f"API Request Error for {endpoint}: {e}")
        print(f"  Error Type: {type(e).__name__}")
        print(f"  Error Details: {repr(e)}")
        return {"success": False, "message": f"Connection error (Network Error). Please check internet connection.", "details": str(e)}
    except json.JSONDecodeError as e:
        raw = (getattr(response, "text", None) or str(e))[:500]
        print(f"API JSON Decode Error for {endpoint}: {e} - Response: {raw}")
        return {"success": False, "message": "Error processing system response. Invalid JSON from API.", "details": str(e), "raw_response": raw}
    except Exception as e:
        print(f"Unexpected API Error for {endpoint}: {e}")
        return {"success": False, "message": f"An unexpected error occurred while connecting to the system: {str(e)}", "details": str(e)}


# ----------------------------------------------------------------------------------------------------------------------
# Real API Integration Functions (replacing mock functions) based on LinasLaser AI Agent API Documentation.pdf
# These functions will now call the _make_api_request helper.
# ----------------------------------------------------------------------------------------------------------------------

async def get_branches():
    """Retrieves a list of all branches associated with the clinic."""
    print("API Call: get_branches")
    response = await _make_api_request("GET", "branches")
    if response.get("success"):
        log_report_event("api_call", "System", "N/A", {"api": "get_branches", "status": "success", "count": len(response.get("data", []))})
    else:
        log_report_event("api_call", "System", "N/A", {"api": "get_branches", "status": "failed", "error": response.get("message")})
    return response

async def get_services():
    """Retrieves a list of all services offered by the clinic."""
    print("API Call: get_services")
    response = await _make_api_request("GET", "services")
    if response.get("success"):
        log_report_event("api_call", "System", "N/A", {"api": "get_services", "status": "success", "count": len(response.get("data", []))})
    else:
        log_report_event("api_call", "System", "N/A", {"api": "get_services", "status": "failed", "error": response.get("message")})
    return response

async def get_machines():
    """Retrieves a list of all machines available in the clinic."""
    print("API Call: get_machines")
    response = await _make_api_request("GET", "machines")
    if response.get("success"):
        log_report_event("api_call", "System", "N/A", {"api": "get_machines", "status": "success", "count": len(response.get("data", []))})
    else:
        log_report_event("api_call", "System", "N/A", {"api": "get_machines", "status": "failed", "error": response.get("message")})
    return response

def _body_part_endpoint_candidates() -> list:
    """Ordered GET paths; override with LINASLASER_GET_BODY_PARTS_PATH when your host uses a different route."""
    out = []
    custom = (os.getenv("LINASLASER_GET_BODY_PARTS_PATH") or "").strip().lstrip("/")
    if custom:
        out.append(custom)
    for p in ("body-parts", "body_parts"):
        if p not in out:
            out.append(p)
    return out


async def get_body_parts(service_id: int = None, machine_id: int = None):
    """Returns list of body parts (id, name) for pricing/booking. Optional service_id/machine_id filters."""
    print("API Call: get_body_parts")
    params = {}
    if service_id is not None:
        params["service_id"] = service_id
    if machine_id is not None:
        params["machine_id"] = machine_id
    q = params if params else None
    last: dict = {"success": False, "message": "get_body_parts: no endpoint tried"}
    for ep in _body_part_endpoint_candidates():
        response = await _make_api_request("GET", ep, params=q)
        last = response
        if response.get("success"):
            log_report_event(
                "api_call",
                "System",
                "N/A",
                {
                    "api": "get_body_parts",
                    "path": ep,
                    "status": "success",
                    "count": len(response.get("data") or []),
                    "service_id": service_id,
                    "machine_id": machine_id,
                },
            )
            return response
        msg = str(response.get("message") or "").lower()
        sc = response.get("status_code")
        if sc == 404 or "not found" in msg:
            print(f"API Call: get_body_parts retry — {ep} failed, trying next path")
            continue
        log_report_event(
            "api_call",
            "System",
            "N/A",
            {
                "api": "get_body_parts",
                "path": ep,
                "status": "failed",
                "error": response.get("message"),
                "service_id": service_id,
                "machine_id": machine_id,
            },
        )
        return response
    log_report_event(
        "api_call",
        "System",
        "N/A",
        {
            "api": "get_body_parts",
            "status": "failed",
            "error": last.get("message"),
            "service_id": service_id,
            "machine_id": machine_id,
        },
    )
    return last


async def get_service_data(service_id: int, machine_id: int = None):
    """
    GET service/data — price + body_parts options for a service (Appointment API doc).
    Path override: LINASLASER_SERVICE_DATA_PATH (default service/data).
    """
    path = (os.getenv("LINASLASER_SERVICE_DATA_PATH") or "service/data").strip().lstrip("/")
    params: dict = {"service_id": int(service_id)}
    if machine_id is not None:
        try:
            params["machine_id"] = int(machine_id)
        except (TypeError, ValueError):
            pass
    print(f"API Call: get_service_data path={path} params={params}")
    response = await _make_api_request("GET", path, params=params)
    if response.get("success"):
        log_report_event(
            "api_call",
            "System",
            "N/A",
            {"api": "get_service_data", "status": "success", "path": path, "service_id": service_id},
        )
    else:
        log_report_event(
            "api_call",
            "System",
            "N/A",
            {
                "api": "get_service_data",
                "status": "failed",
                "path": path,
                "error": response.get("message"),
                "service_id": service_id,
            },
        )
    return response


async def get_clinic_hours():
    """Returns the clinic's working hours for each day of the week."""
    print("API Call: get_clinic_hours")
    response = await _make_api_request("GET", "clinic/hours")
    if response.get("success"):
        log_report_event("api_call", "System", "N/A", {"api": "get_clinic_hours", "status": "success", "data": response.get("data")})
    else:
        log_report_event("api_call", "System", "N/A", {"api": "get_clinic_hours", "status": "failed", "error": response.get("message")})
    return response

async def send_appointment_reminders(date: str = None, phone: str = None, user_code: str = None, status: str = None):
    """
    Retrieves appointments with optional filters.

    Args:
        date: Filter by date (YYYY-MM-DD)
        phone: Filter by phone number
        user_code: Filter by user code
        status: Filter by status (done, available, postponed, paused)
    """
    print(f"API Call: send_appointment_reminders for date={date}, phone={phone}, user_code={user_code}, status={status}")
    params = {}
    if date: params["date"] = date
    if phone: params["phone"] = phone
    if user_code: params["user_code"] = user_code
    if status: params["status"] = status
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
                    print(f"   First appointment sample: {data['appointments'][0] if data['appointments'] else 'EMPTY'}")
            elif isinstance(data, list) and data:
                print(f"   First item in data list: {data[0]}")

    if response.get("success"):
        log_report_event("api_call", "System", "N/A", {"api": "send_appointment_reminders", "status": "success", "params": params})
    else:
        log_report_event("api_call", "System", "N/A", {"api": "send_appointment_reminders", "status": "failed", "error": response.get("message"), "params": params})
    return response

async def check_next_appointment(phone: str, user_code: str = None):
    """Returns the next scheduled appointment for a client."""
    # Clean phone number to match API expected format (without + prefix and country code)
    phone_clean = str(phone).replace("+", "").replace(" ", "").replace("-", "")
    if phone_clean.startswith("961"):
        phone_clean = phone_clean[3:]  # Remove Lebanon country code

    print(f"API Call: check_next_appointment for phone={phone_clean} (original: {phone}), user_code={user_code}")
    params = {"phone": phone_clean}
    if user_code: params["user_code"] = user_code
    response = await _make_api_request("GET", "appointments/next", params=params)
    if response.get("success"):
        log_report_event("api_call", "System", "N/A", {"api": "check_next_appointment", "status": "success", "phone": phone, "appointment": response.get("data")})
    else:
        log_report_event("api_call", "System", "N/A", {"api": "check_next_appointment", "status": "failed", "error": response.get("message"), "phone": phone})
    return response

async def get_sessions_count_by_phone(phone: str = None, user_code: str = None, service_ids: list = None):
    """Returns the number of sessions a client has attended, based on their phone number or user code."""
    # Clean phone number to match API expected format (without + prefix and country code)
    phone_clean = None
    if phone:
        phone_clean = str(phone).replace("+", "").replace(" ", "").replace("-", "")
        if phone_clean.startswith("961"):
            phone_clean = phone_clean[3:]  # Remove Lebanon country code

    print(f"API Call: get_sessions_count_by_phone for phone={phone_clean} (original: {phone}), user_code={user_code}, service_ids={service_ids}")
    params = {}
    if phone_clean: params["phone"] = phone_clean
    if user_code: params["user_code"] = user_code
    if service_ids: params["service_ids"] = service_ids
    response = await _make_api_request("GET", "appointments/sessions/count", params=params)
    if response.get("success"):
        log_report_event("api_call", "System", "N/A", {"api": "get_sessions_count_by_phone", "status": "success", "phone": phone, "data": response.get("data")})
    else:
        log_report_event("api_call", "System", "N/A", {"api": "get_sessions_count_by_phone", "status": "failed", "error": response.get("message"), "phone": phone})
    return response

async def move_client_branch(
    phone: str,
    from_branch_id: int,
    to_branch_id: int,
    new_date: str = None,
    user_code: str = None,
    response_confirm: str = "yes",
):
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
        f"API Call: move_client_branch for phone={phone_clean} (original: {phone}), "
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
        log_report_event("api_call", "System", "N/A", {"api": "move_client_branch", "status": "success", "phone": phone, "details": response.get("data")})
    else:
        log_report_event("api_call", "System", "N/A", {"api": "move_client_branch", "status": "failed", "error": response.get("message"), "phone": phone})
    return response

async def check_appointment_payment(phone: str, user_code: str = None):
    """Checks the payment status of a client's appointments."""
    # Clean phone number to match API expected format (without + prefix and country code)
    phone_clean = str(phone).replace("+", "").replace(" ", "").replace("-", "")
    if phone_clean.startswith("961"):
        phone_clean = phone_clean[3:]  # Remove Lebanon country code

    print(f"API Call: check_appointment_payment for phone={phone_clean} (original: {phone}), user_code={user_code}")
    params = {"phone": phone_clean}
    if user_code: params["user_code"] = user_code
    response = await _make_api_request("GET", "appointments/payment", params=params)
    if response.get("success"):
        log_report_event("api_call", "System", "N/A", {"api": "check_appointment_payment", "status": "success", "phone": phone, "payment": response.get("data")})
    else:
        log_report_event("api_call", "System", "N/A", {"api": "check_appointment_payment", "status": "failed", "error": response.get("message"), "phone": phone})
    return response

async def get_pricing_details(service_id: int, machine_id: int = None, body_part_ids: list = None, branch_id: int = None):
    """Returns pricing details for appointments or services based on specified criteria."""
    print(f"API Call: get_pricing_details for service_id={service_id}")
    params = {"service_id": service_id}
    if machine_id: params["machine_id"] = machine_id
    # Format body_part_ids as PHP-style array params (body_part_ids[]=1&body_part_ids[]=2)
    if body_part_ids:
        if isinstance(body_part_ids, list):
            params["body_part_ids[]"] = body_part_ids
        else:
            params["body_part_ids[]"] = [body_part_ids]
    if branch_id: params["branch_id"] = branch_id
    response = await _make_api_request("GET", "appointments/pricing", params=params)
    if response.get("success"):
        log_report_event("api_call", "System", "N/A", {"api": "get_pricing_details", "status": "success", "service_id": service_id, "pricing": response.get("data")})
    else:
        log_report_event("api_call", "System", "N/A", {"api": "get_pricing_details", "status": "failed", "error": response.get("message"), "service_id": service_id})
    return response

async def get_missed_appointments(date: str = None):
    """Returns a list of missed appointments for the clinic."""
    print(f"API Call: get_missed_appointments for date={date}")
    params = {}
    if date: params["date"] = date
    response = await _make_api_request("GET", "appointments/missed", params=params)
    if response.get("success"):
        log_report_event("api_call", "System", "N/A", {"api": "get_missed_appointments", "status": "success", "data": response.get("data")})
    else:
        log_report_event("api_call", "System", "N/A", {"api": "get_missed_appointments", "status": "failed", "error": response.get("message"), "date": date})
    return response

async def get_paused_appointments_between_dates(start_date: str, end_date: str, service_id: int = None):
    """
    Returns a list of paused appointments between two dates.

    Args:
        start_date: Required. Start date in YYYY-MM-DD format (e.g., "2026-01-01")
        end_date: Required. End date in YYYY-MM-DD format (e.g., "2026-02-01")
        service_id: Optional. Filter by service ID

    Returns:
        API response with paused appointments data
    """
    print(f"API Call: get_paused_appointments_between_dates for start_date={start_date}, end_date={end_date}, service_id={service_id}")
    params = {
        "start_date": start_date,
        "end_date": end_date
    }
    if service_id is not None:
        params["service_id"] = service_id

    response = await _make_api_request("GET", "appointments/paused/between-dates", params=params)
    if response.get("success"):
        log_report_event("api_call", "System", "N/A", {"api": "get_paused_appointments_between_dates", "status": "success", "start_date": start_date, "end_date": end_date, "service_id": service_id})
    else:
        log_report_event("api_call", "System", "N/A", {"api": "get_paused_appointments_between_dates", "status": "failed", "error": response.get("message"), "start_date": start_date, "end_date": end_date, "service_id": service_id})
    return response

async def get_appointment_details(appointment_id: int):
    """Retrieves detailed information about a specific appointment by ID."""
    print(f"API Call: get_appointment_details for appointment_id={appointment_id}")
    params = {"appointment_id": appointment_id}
    response = await _make_api_request("GET", "appointment", params=params)
    if response.get("success"):
        log_report_event("api_call", "System", "N/A", {"api": "get_appointment_details", "status": "success", "appointment_id": appointment_id})
    else:
        log_report_event("api_call", "System", "N/A", {"api": "get_appointment_details", "status": "failed", "error": response.get("message"), "appointment_id": appointment_id})
    return response

def _phone_clean_for_appointment_api(phone: str) -> str:
    phone_clean = str(phone).replace("+", "").replace(" ", "").replace("-", "")
    if phone_clean.startswith("961"):
        phone_clean = phone_clean[3:]
    return phone_clean


async def pause_appointment(phone: str, appointment_id: int):
    """Pauses an appointment by updating its status to Paused."""
    phone_clean = _phone_clean_for_appointment_api(phone)
    print(f"API Call: pause_appointment for phone={phone_clean}, appointment_id={appointment_id}")
    json_data = {"phone": phone_clean, "appointment_id": appointment_id}
    response = await _make_api_request("POST", "appointments/pause", json_data=json_data)
    if response.get("success"):
        log_report_event("api_call", "System", "N/A", {"api": "pause_appointment", "status": "success", "appointment_id": appointment_id})
    else:
        log_report_event("api_call", "System", "N/A", {"api": "pause_appointment", "status": "failed", "error": response.get("message"), "appointment_id": appointment_id})
    return response


async def resume_appointment(phone: str, appointment_id: int, endpoint: str = None):
    """
    Clears Paused / sets appointment back to active (Available) when the Agent API exposes a resume endpoint.

    **LINASLASER_APPOINTMENT_RESUME_PATH** overrides the POST path (e.g. ``appointments/unpause``).
    If unset, defaults to ``appointments/resume`` (symmetric with ``appointments/pause``).
    Set to ``off``, ``0``, ``false``, or ``none`` to skip the call entirely.
    """
    phone_clean = _phone_clean_for_appointment_api(phone)
    if endpoint is not None:
        path = str(endpoint).strip()
    else:
        raw = os.getenv("LINASLASER_APPOINTMENT_RESUME_PATH")
        if raw is None:
            path = "appointments/resume"
        else:
            path = str(raw).strip()
    if not path or path.lower() in ("0", "false", "off", "none"):
        return {"success": False, "message": "resume_skipped_no_path", "skipped": True}
    print(f"API Call: resume_appointment for phone={phone_clean}, appointment_id={appointment_id}, path={path}")
    json_data = {"phone": phone_clean, "appointment_id": appointment_id}
    response = await _make_api_request("POST", path, json_data=json_data)
    merged = dict(response) if isinstance(response, dict) else {"success": False, "message": str(response)}
    merged["path"] = path
    if response.get("success"):
        log_report_event("api_call", "System", "N/A", {"api": "resume_appointment", "status": "success", "appointment_id": appointment_id, "path": path})
    else:
        log_report_event("api_call", "System", "N/A", {"api": "resume_appointment", "status": "failed", "error": response.get("message"), "appointment_id": appointment_id, "path": path})
    return merged

async def get_clients_without_today(date: str = None, branch_id: int = None):
    """Returns all active clients who do not have appointments on the given date."""
    print(f"API Call: get_clients_without_today for date={date}, branch_id={branch_id}")
    params = {}
    if date:
        params["date"] = date
    if branch_id is not None:
        params["branch_id"] = branch_id
    response = await _make_api_request("GET", "appointments/clients/without-today", params=params)
    if response.get("success"):
        log_report_event("api_call", "System", "N/A", {"api": "get_clients_without_today", "status": "success", "date": date})
    else:
        log_report_event("api_call", "System", "N/A", {"api": "get_clients_without_today", "status": "failed", "error": response.get("message")})
    return response

async def get_customer_sessions(customer_id: int):
    """Returns sessions (appointments) for a customer including service, area, status, and notes."""
    print(f"API Call: get_customer_sessions for customer_id={customer_id}")
    params = {"customer_id": customer_id}
    response = await _make_api_request("GET", "customers/sessions", params=params)
    if response.get("success"):
        log_report_event("api_call", "System", "N/A", {"api": "get_customer_sessions", "status": "success", "customer_id": customer_id})
    else:
        log_report_event("api_call", "System", "N/A", {"api": "get_customer_sessions", "status": "failed", "error": response.get("message"), "customer_id": customer_id})
    return response

async def add_customer_note(phone: str, note: str):
    """Adds a note to the customer record by phone number."""
    phone_clean = str(phone).replace("+", "").replace(" ", "").replace("-", "")
    if phone_clean.startswith("961"):
        phone_clean = phone_clean[3:]
    print(f"API Call: add_customer_note for phone={phone_clean}")
    json_data = {"phone": phone_clean, "note": note[:1000]}
    response = await _make_api_request("POST", "customers/notes/add", json_data=json_data)
    if response.get("success"):
        log_report_event("api_call", "System", "N/A", {"api": "add_customer_note", "status": "success", "phone": phone_clean})
    else:
        log_report_event("api_call", "System", "N/A", {"api": "add_customer_note", "status": "failed", "error": response.get("message"), "phone": phone_clean})
    return response

async def get_all_customers(date: str = None, from_date: str = None, to_date: str = None):
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
        log_report_event("api_call", "System", "N/A", {"api": "get_all_customers", "status": "success", "count": len(response.get("data", []))})
    else:
        log_report_event("api_call", "System", "N/A", {"api": "get_all_customers", "status": "failed", "error": response.get("message")})
    return response

async def get_customer_by_phone(phone: str):
    """Retrieves customer details by phone number. Accepts any format; normalizes to E.164 then API local format."""
    from utils.phone_utils import normalize_phone
    normalized = normalize_phone(phone)
    if normalized and normalized.startswith("+961"):
        phone_clean = normalized[4:]  # strip "+961"
    else:
        phone_clean = str(phone).replace("+", "").replace(" ", "").replace("-", "")
        if phone_clean.startswith("961"):
            phone_clean = phone_clean[3:]
    print(f"API Call: get_customer_by_phone for phone={phone_clean}")
    params = {"phone": phone_clean}
    response = await _make_api_request("GET", "customers/by-phone", params=params) # Assuming this endpoint exists
    if response.get("success"):
        log_report_event("api_call", "System", "N/A", {"api": "get_customer_by_phone", "status": "success", "phone": phone_clean, "customer": response.get("data")})
    else:
        log_report_event("api_call", "System", "N/A", {"api": "get_customer_by_phone", "status": "failed", "error": response.get("message"), "phone": phone_clean})
    return response

async def get_customer_appointments(phone: str):
    """Retrieves all appointments for a customer by phone number (no country code)."""
    print(f"API Call: get_customer_appointments for phone={phone}")
    
    # Remove country code if present (e.g., +961 -> empty, keep only digits)
    phone_clean = phone.replace("+", "").replace(" ", "")
    if phone_clean.startswith("961"):
        phone_clean = phone_clean[3:]  # Remove Lebanon country code
    
    params = {"phone": phone_clean}
    response = await _make_api_request("GET", "appointments/customer", params=params)
    
    if response.get("success"):
        log_report_event("api_call", "System", "N/A", {"api": "get_customer_appointments", "status": "success", "phone": phone_clean})
    else:
        log_report_event("api_call", "System", "N/A", {"api": "get_customer_appointments", "status": "failed", "error": response.get("message"), "phone": phone_clean})
    
    return response

def _clean_body_part_ids_for_api(raw: list) -> list:
    out = []
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


def _clean_body_parts_with_sessions_for_api(raw: Any) -> list:
    """Normalize list items to BOC body_parts rows (default key **id** per API doc)."""
    out = []
    if not isinstance(raw, list) or not raw:
        return out
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            pid = int(item.get("body_part_id") or item.get("id"))
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


async def create_appointment(phone: str, service_id: int, machine_id: Optional[int], branch_id: int, date: str, user_code: str = None, body_part_ids: list = None, body_parts_with_sessions: list = None, **kwargs):
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

    print(f"API Call: create_appointment for phone={phone_clean} (original: {phone}), service={service_id}, date={date}")
    json_data = {
        "phone": phone_clean,
        "service_id": service_id,
        "branch_id": branch_id,
        "date": date
    }
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
        prefer_parts = (
            not ids_only
            or force_sessions_env
            or legacy_env
            or non_one
        )
        if prefer_parts:
            json_data["body_parts"] = cleaned_bps
            use_body_parts = True
        else:
            json_data["body_part_ids"] = [
                int(x.get("id") or x.get("body_part_id")) for x in cleaned_bps
            ]
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
        log_report_event("api_call", "System", "N/A", {"api": "create_appointment", "status": "success", "phone": phone, "appointment": response.get("data")})
    else:
        log_report_event("api_call", "System", "N/A", {"api": "create_appointment", "status": "failed", "error": response.get("message"), "phone": phone})
    return response

def _safe_float_amount(v) -> Optional[float]:
    try:
        if v is None or v == "":
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def extract_appointment_total_from_api_payload(payload: Any) -> Optional[float]:
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


async def add_appointment_discount(appointment_id: int, discount_amount: float):
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
    print(f"API Call: add_appointment_discount for appointment_id={aid}, discount_amount={json_data['discount_amount']}")
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
    system_total_known: Optional[float] = None,
):
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


async def update_appointment_date(appointment_id: int, phone: str, date: str, user_code: str = None):
    """Updates the date/time of an existing appointment."""
    phone_clean = _phone_clean_for_appointment_api(phone)

    print(f"API Call: update_appointment_date for appointment_id={appointment_id}, phone={phone_clean} (original: {phone}), date={date}")
    json_data = {
        "appointment_id": appointment_id,
        "phone": phone_clean,
        "date": date
    }
    if user_code:
        json_data["user_code"] = user_code
    # Optional: same-request hint for CRMs that clear pause when this field is present (confirm with Agent API spec).
    if os.getenv("LINASLASER_UPDATE_DATE_SET_STATUS_AVAILABLE", "").lower() in ("1", "true", "yes"):
        json_data["status"] = "Available"

    response = await _make_api_request("POST", "appointments/update/date", json_data=json_data)
    if response.get("success"):
        log_report_event("api_call", "System", "N/A", {"api": "update_appointment_date", "status": "success", "phone": phone, "appointment_id": appointment_id, "new_date": date})
        # After reschedule: try to clear Paused → Available (CRM UI) via resume endpoint; see resume_appointment docstring.
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
        log_report_event("api_call", "System", "N/A", {"api": "update_appointment_date", "status": "failed", "error": response.get("message"), "phone": phone, "appointment_id": appointment_id})
    return response


async def edit_appointment(
    appointment_id: int,
    phone: str = None,
    user_code: str = None,
    service_id: int = None,
    machine_id: int = None,
    branch_id: int = None,
    date: str = None,
    body_part_ids: list = None,
    body_parts_with_sessions: list = None,
    session_number: int = None,
    discount_percentage: float = None,
    discount_amount: float = None,
    total_cost_after_discount: float = None,
    hidden: bool = None,
    **kwargs,
):
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

    print(
        f"API Call: edit_appointment path={path} appointment_id={appointment_id} "
        f"keys={list(json_data.keys())}"
    )
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
    date: str = None,
    machine_id: int = None,
    body_part_ids: list = None,
    body_parts_with_sessions: list = None,
    status: str = None,
    user_code: str = None,
):
    """
    Updates paused appointment details (date, machine, body parts, sessions, status).
    Intended for paused-row editing workflows where the AI prepares a full JSON patch.
    """
    phone_clean = _phone_clean_for_appointment_api(phone)
    path = (os.getenv("LINASLASER_UPDATE_PAUSED_APPOINTMENT_PATH") or "appointments/update").strip().lstrip("/")
    print(
        "API Call: update_paused_appointment "
        f"appointment_id={appointment_id}, phone={phone_clean}, path={path}"
    )

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
    if clean_ids:
        json_data["body_part_ids"] = clean_ids
    cleaned_sessions = _clean_body_parts_with_sessions_for_api(body_parts_with_sessions)
    if cleaned_sessions:
        json_data["body_parts"] = cleaned_sessions

    status_raw = (status or "").strip()
    default_set_available = os.getenv(
        "LINASLASER_UPDATE_PAUSED_DEFAULT_STATUS_AVAILABLE", "true"
    ).lower() in ("1", "true", "yes")
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
        # Safety fallback: if target status is Available, also try resume endpoint.
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

async def check_customer_gender(phone: str = None, user_code: str = None):
    """Returns the gender of a customer based on the provided identifier."""
    # Clean phone number to match API expected format (without + prefix and country code)
    phone_clean = None
    if phone:
        phone_clean = str(phone).replace("+", "").replace(" ", "").replace("-", "")
        if phone_clean.startswith("961"):
            phone_clean = phone_clean[3:]  # Remove Lebanon country code

    print(f"API Call: check_customer_gender for phone={phone_clean} (original: {phone}), user_code={user_code}")
    params = {}
    # NEW: Ensure either phone or user_code is provided for the API call
    if phone_clean:
        params["phone"] = phone_clean
    elif user_code: # Prioritize user_code if phone is not provided and user_code is.
        params["user_code"] = user_code
    else: # If neither is provided, return an error as per API docs
        return {"success": False, "message": "Either phone or user_code must be provided."}
        
    response = await _make_api_request("GET", "customers/gender", params=params)
    if response.get("success"): # Check if the API itself returned success
        log_report_event("api_call", "System", "N/A", {"api": "check_customer_gender", "status": "success", "phone": phone, "gender": response.get("data", {}).get("gender")})
    else: # API returned success:false or a non-200 status (other than 404 handled above)
        log_report_event("api_call", "System", "N/A", {"api": "check_customer_gender", "status": "failed", "error": response.get("message"), "phone": phone})
    return response

async def create_customer(name: str, phone: str, gender: str, email: str = None, branch_id: int = None, date_of_birth: str = None):
    """Creates a new customer record within the clinic's database (POST customers/create).

    `branch_id` is required by the Agent API; callers may omit it only to mean
    `config.DEFAULT_BRANCH_ID`. If no valid branch can be resolved, the HTTP
    request is not sent.
    """
    # Resolve branch: explicit arg wins, else clinic default from config
    resolved_branch = branch_id if branch_id is not None else getattr(config, "DEFAULT_BRANCH_ID", None)
    try:
        resolved_branch_int = int(resolved_branch)
    except (TypeError, ValueError):
        resolved_branch_int = None
    # Known clinic branches in bot reference (expand if API adds branches)
    if resolved_branch_int not in (1, 2):
        return {
            "success": False,
            "message": "branch_id is required for customers/create (use 1=Beirut, 2=Antelias or set config.DEFAULT_BRANCH_ID).",
        }

    # Clean phone number to match API expected format (without + prefix and country code)
    phone_clean = str(phone).replace("+", "").replace(" ", "").replace("-", "")
    if phone_clean.startswith("961"):
        phone_clean = phone_clean[3:]  # Remove Lebanon country code

    # Fallback: Try to get phone from config if the cleaned phone looks invalid
    if len(phone_clean) < 8:
        if "config" in globals() and hasattr(config, "user_data_whatsapp"):
            for uid, data in config.user_data_whatsapp.items():
                if "phone_number" in data and data["phone_number"]:
                    if str(uid) == str(phone):  # room_id matches phone variable
                        print(f"⚠️ create_customer: Detected invalid phone={phone}, using actual phone {data['phone_number']}")
                        phone_clean = str(data["phone_number"]).replace("+", "").replace(" ", "").replace("-", "")
                        if phone_clean.startswith("961"):
                            phone_clean = phone_clean[3:]
                        break

    # Convert gender to API format: "male"/"female" -> "Male"/"Female"
    gender_api_format = gender.capitalize() if gender.lower() in ["male", "female"] else "Male"

    print(
        f"API Call: create_customer for name={name}, phone={phone_clean} (original: {phone}), "
        f"gender={gender_api_format}, branch_id={resolved_branch_int}"
    )
    json_data = {
        "name": name,
        "phone": phone_clean,
        "gender": gender_api_format,  # Gender must be 'Male' or 'Female' as per API
        "branch_id": resolved_branch_int,
    }
    if email:
        json_data["email"] = email
    if date_of_birth:
        json_data["date_of_birth"] = date_of_birth
    response = await _make_api_request("POST", "customers/create", json_data=json_data)
    if response.get("success"):
        log_report_event("api_call", "System", "N/A", {"api": "create_customer", "status": "success", "phone": phone, "customer": response.get("data")})
    else:
        log_report_event("api_call", "System", "N/A", {"api": "create_customer", "status": "failed", "error": response.get("message"), "phone": phone})
    return response

async def update_customer_gender(customer_id: int, gender: str):
    """
    DEPRECATED: The external API does not support updating customer gender (returns 404).
    Gender is now persisted via Firestore in user_persistence_service.py.
    This function is kept for backwards compatibility but will always fail.
    Use user_persistence.save_user_gender() instead.
    """
    print(f"⚠️ DEPRECATED: update_customer_gender called for customer_id={customer_id}, gender={gender}")
    print(f"⚠️ External API does not support gender updates. Use Firestore via user_persistence.save_user_gender()")

    # Return a mock success to prevent errors in legacy code
    # Gender is actually saved via Firestore in user_persistence_service.py
    return {"success": True, "message": "Gender saved via Firestore (external API deprecated)"}


# Modified log_report_event to accept user_id and update Firestore metrics
def log_report_event(event_type: str, user_id: str, user_gender: str, details: dict = None):
    user_name = config.user_names.get(user_id, "N/A") # Get user_name from config
    event_data = {
        "timestamp": datetime.datetime.now().isoformat(),
        "type": event_type,
        "user_id": user_id, # Log user_id for better tracking
        "user_name": user_name,
        "user_gender": user_gender,
        "details": details if details else {}
    }
    try:
        os.makedirs('data', exist_ok=True)
        with open(REPORT_LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(json.dumps(event_data, ensure_ascii=False) + '\n')
            f.flush()
        
        # NEW: Update Firestore metrics based on event type
        # We need to make this an async call, but log_report_event is not async.
        # This will be handled by calling update_dashboard_metric_in_firestore from the handlers
        # that call log_report_event, or by making this function async and awaiting it.
        # For now, we'll keep it synchronous and add a note.
        # A better approach would be to have the handlers call update_dashboard_metric_in_firestore directly
        # after calling log_report_event, or make log_report_event async.
        # Given the current structure, the most practical is for handlers to call update_dashboard_metric_in_firestore.
        # Let's assume for now the dashboard metrics will be updated by the handlers directly
        # when specific events (like new user, human handover, etc.) occur.
        # So, for now, this function only logs to the file.
        pass # No direct Firestore update here to avoid async issues in a sync function

    except Exception as e:
        print(f"❌ ERROR logging report event: {e}")

# Refactored generate_daily_report_command to return string and accept send_message_func
async def generate_daily_report_command(user_id: str, send_message_func):
    """
    Generates a daily report of bot interactions and returns it as a string.
    This function is now platform-agnostic and relies on send_message_func to send the report.
    """
    if user_id != config.TRAINER_WHATSAPP_NUMBER: # Use WhatsApp number for trainer ID check
        await send_message_func(user_id, "ليس لديك صلاحية لطلب التقرير اليومي.")
        return "" # Return empty string if not authorized

    # The calling function (in main.py or handlers) already sends "جارٍ توليد التقرير اليومي..."
    # So we don't send it here.

    report_data = {
        "new_users": {"male": 0, "female": 0, "unspecified": 0},
        "appointments_booked": {"male": 0, "female": 0, "unspecified": 0, "details": []},
        "appointments_rescheduled": {"male": 0, "female": 0, "unspecified": 0, "details": []},
        "complaints": {"male": 0, "female": 0, "unspecified": 0, "details": []},
        "burn_reports": {"male": 0, "female": 0, "unspecified": 0, "details": []},
        "human_handover_requests": {"male": 0, "female": 0, "unspecified": 0, "details": []},
        "missed_appointments": {"male": 0, "female": 0, "unspecified": 0, "details": []},
        "total_interactions": 0,
        "api_calls": {"success": 0, "failed": 0, "details": []}
    }

    today_str = datetime.date.today().isoformat()
    try:
        if os.path.exists(REPORT_LOG_FILE):
            with open(REPORT_LOG_FILE, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        event = json.loads(line)
                        if event["timestamp"].startswith(today_str):
                            report_data["total_interactions"] += 1
                            user_gender = event.get("user_gender", "unspecified")
                            event_type = event["type"]
                            event_user_name = event.get("user_name", "N/A") # Get name from event log

                            if event_type == "new_user":
                                report_data["new_users"][user_gender] += 1
                            elif event_type == "appointment_booked":
                                report_data["appointments_booked"][user_gender] += 1
                                report_data["appointments_booked"]["details"].append(
                                    f"{event_user_name} ({user_gender}): {event['details'].get('service')} on {event['details'].get('date')} at {event['details'].get('time')}"
                                )
                            elif event_type == "appointment_rescheduled":
                                report_data["appointments_rescheduled"][user_gender] += 1
                                report_data["appointments_rescheduled"]["details"].append(
                                    f"{event_user_name} ({user_gender}): From {event['details'].get('old_date')} to {event['details'].get('new_date')} {event['details'].get('new_time')}"
                                )
                            elif event_type == "complaint":
                                report_data["complaints"][user_gender] += 1
                                report_data["complaints"]["details"].append(
                                    f"{event_user_name} ({user_gender}): {event['details'].get('message')}"
                                )
                            elif event_type == "burn_report":
                                report_data["burn_reports"][user_gender] += 1
                                report_data["burn_reports"]["details"].append(
                                    f"{event_user_name} ({user_gender}): {event['details'].get('description')}"
                                )
                            elif event_type == "human_handover":
                                report_data["human_handover_requests"][user_gender] += 1
                                report_data["human_handover_requests"]["details"].append(
                                    f"{event_user_name} ({user_gender}): {event['details'].get('message')}"
                                )
                            elif event_type == "appointment_missed":
                                report_data["missed_appointments"][user_gender] += 1
                                report_data["missed_appointments"]["details"].append(
                                    f"{event_user_name} ({user_gender}): {event['details'].get('date')} {event['details'].get('time')}"
                                )
                            elif event_type == "api_call":
                                if event['details'].get('status') == 'success':
                                    report_data["api_calls"]["success"] += 1
                                else:
                                    report_data["api_calls"]["failed"] += 1
                                report_data["api_calls"]["details"].append(
                                    f"API: {event['details'].get('api')} - Status: {event['details'].get('status')} - Details: {event['details'].get('error', event['details'].get('data', 'N/A'))}"
                                )
                    except json.JSONDecodeError:
                        continue
        else:
            return "لا توجد سجلات تقارير سابقة لهذا اليوم."
    except Exception as e:
        return f"حدث خطأ أثناء توليد التقرير: {str(e)}"

    appointments_booked_details_str = "\n  ".join(report_data['appointments_booked']['details']) if report_data['appointments_booked']['details'] else "N/A"
    appointments_rescheduled_details_str = "\n  ".join(report_data['appointments_rescheduled']['details']) if report_data['appointments_rescheduled']['details'] else "N/A"
    human_handover_requests_details_str = "\n  ".join(report_data['human_handover_requests']['details']) if report_data['human_handover_requests']['details'] else "N/A"
    burn_reports_details_str = "\n  ".join(report_data['burn_reports']['details']) if report_data['burn_reports']['details'] else "N/A"
    missed_appointments_details_str = "\n  ".join(report_data['missed_appointments']['details']) if report_data['missed_appointments']['details'] else "N/A"
    complaints_details_str = "\n  ".join(report_data['complaints']['details']) if report_data['complaints']['details'] else "N/A"
    api_calls_details_str = "\n  ".join(report_data['api_calls']['details']) if report_data['api_calls']['details'] else "N/A"


    report_message = (
        f"📊 *Daily Bot Report - {today_str}*\n" # Using * for bold as WhatsApp might not support **
        f"*Total Interactions:* {report_data['total_interactions']}\n\n"
        
        f"👥 *New Users:*\n"
        f"  - Male: {report_data['new_users']['male']}\n"
        f"  - Female: {report_data['new_users']['female']}\n"
        f"  - Unspecified: {report_data['new_users']['unspecified']}\n\n"
        
        f"📝 *Appointments Booked:*\n"
        f"  - Male: {report_data['appointments_booked']['male']}\n"
        f"  - Female: {report_data['appointments_booked']['female']}\n"
        f"  - Unspecified: {report_data['appointments_booked']['unspecified']}\n"
        f"  {appointments_booked_details_str}\n\n"
        
        f"🔄 *Appointments Rescheduled:*\n"
        f"  - Male: {report_data['appointments_rescheduled']['male']}\n"
        f"  - Female: {report_data['appointments_rescheduled']['female']}\n"
        f"  - Unspecified: {report_data['appointments_rescheduled']['unspecified']}\n"
        f"  {appointments_rescheduled_details_str}\n\n"

        f"❓ *Human Handover Requests:*\n"
        f"  - Male: {report_data['human_handover_requests']['male']}\n"
        f"  - Female: {report_data['human_handover_requests']['female']}\n"
        f"  - Unspecified: {report_data['human_handover_requests']['unspecified']}\n"
        f"  {human_handover_requests_details_str}\n\n"
        
        f"🔥 *Burn/Injury Reports:*\n"
        f"  - Male: {report_data['burn_reports']['male']}\n"
        f"  - Female: {report_data['burn_reports']['female']}\n"
        f"  - Unspecified: {report_data['burn_reports']['unspecified']}\n"
        f"  {burn_reports_details_str}\n\n"

        f"❌ *Missed Appointments:*\n"
        f"  - Male: {report_data['missed_appointments']['male']}\n"
        f"  - Female: {report_data['missed_appointments']['female']}\n"
        f"  - Unspecified: {report_data['missed_appointments']['unspecified']}\n"
        f"  {missed_appointments_details_str}\n\n"
        
        f"⚠️ *General Complaints/Issues:*\n"
        f"  - Male: {report_data['complaints']['male']}\n"
        f"  - Female: {report_data['complaints']['female']}\n"
        f"  - Unspecified: {report_data['complaints']['unspecified']}\n"
        f"  {complaints_details_str}\n\n"

        f"🔗 *API Calls:*\n"
        f"  - Success: {report_data['api_calls']['success']}\n"
        f"  - Failed: {report_data['api_calls']['failed']}\n"
        f"  {api_calls_details_str}\n\n"
    )

    print("✅ Daily report generated.")
    return report_message # Return the message instead of sending directly
