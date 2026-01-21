import datetime
import json
import os
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
        print(f"API JSON Decode Error for {endpoint}: {e} - Response: {response.text}")
        # This catch-all for JSONDecodeError is important if the API returns malformed JSON even for 200 responses
        return {"success": False, "message": f"Error processing system response. Please contact support. Invalid JSON from API.", "details": str(e), "raw_response": response.text}
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

async def get_clinic_hours():
    """Returns the clinic's working hours for each day of the week."""
    print("API Call: get_clinic_hours")
    response = await _make_api_request("GET", "clinic/hours")
    if response.get("success"):
        log_report_event("api_call", "System", "N/A", {"api": "get_clinic_hours", "status": "success", "data": response.get("data")})
    else:
        log_report_event("api_call", "System", "N/A", {"api": "get_clinic_hours", "status": "failed", "error": response.get("message")})
    return response

async def send_appointment_reminders(date: str = None, phone: str = None, user_code: str = None):
    """Triggers the sending of appointment reminders to clients."""
    print(f"API Call: send_appointment_reminders for date={date}, phone={phone}, user_code={user_code}")
    params = {}
    if date: params["date"] = date
    if phone: params["phone"] = phone
    if user_code: params["user_code"] = user_code
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

async def move_client_branch(phone: str, from_branch_id: int, to_branch_id: int, new_date: str, user_code: str = None, response_confirm: str = "yes"):
    """Moves a client's future appointments to a different branch."""
    # Clean phone number to match API expected format (without + prefix and country code)
    phone_clean = str(phone).replace("+", "").replace(" ", "").replace("-", "")
    if phone_clean.startswith("961"):
        phone_clean = phone_clean[3:]  # Remove Lebanon country code

    print(f"API Call: move_client_branch for phone={phone_clean} (original: {phone}), from={from_branch_id}, to={to_branch_id}, date={new_date}")
    json_data = {
        "phone": phone_clean,
        "from_branch_id": from_branch_id,
        "to_branch_id": to_branch_id,
        "new_date": new_date,
        "response": response_confirm
    }
    if user_code: json_data["user_code"] = user_code
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

async def get_customer_by_phone(phone: str):
    print(f"API Call: get_customer_by_phone for phone={phone}")
    phone_clean = str(phone).replace("+", "").replace(" ", "")
    if phone_clean.startswith("961"):
        phone_clean = phone_clean[3:]

    """Retrieves customer details by phone number."""
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

async def create_appointment(phone: str, service_id: int, machine_id: int, branch_id: int, date: str, user_code: str = None, body_part_ids: list = None):
    """Creates a new appointment record."""
    # Clean phone number to match API expected format (without + prefix and country code)
    phone_clean = str(phone).replace("+", "").replace(" ", "").replace("-", "")
    if phone_clean.startswith("961"):
        phone_clean = phone_clean[3:]  # Remove Lebanon country code

    print(f"API Call: create_appointment for phone={phone_clean} (original: {phone}), service={service_id}, date={date}")
    json_data = {
        "phone": phone_clean,
        "service_id": service_id,
        "machine_id": machine_id,
        "branch_id": branch_id,
        "date": date
    }
    if user_code: json_data["user_code"] = user_code
    if body_part_ids: json_data["body_part_ids"] = body_part_ids
    response = await _make_api_request("POST", "appointments/create", json_data=json_data)
    if response.get("success"):
        log_report_event("api_call", "System", "N/A", {"api": "create_appointment", "status": "success", "phone": phone, "appointment": response.get("data")})
    else:
        log_report_event("api_call", "System", "N/A", {"api": "create_appointment", "status": "failed", "error": response.get("message"), "phone": phone})
    return response

async def update_appointment_date(appointment_id: int, phone: str, date: str, user_code: str = None):
    """Updates the date/time of an existing appointment."""
    # Clean phone number to match API expected format (without + prefix and country code)
    phone_clean = str(phone).replace("+", "").replace(" ", "").replace("-", "")
    if phone_clean.startswith("961"):
        phone_clean = phone_clean[3:]  # Remove Lebanon country code

    print(f"API Call: update_appointment_date for appointment_id={appointment_id}, phone={phone_clean} (original: {phone}), date={date}")
    json_data = {
        "appointment_id": appointment_id,
        "phone": phone_clean,
        "date": date
    }
    if user_code: json_data["user_code"] = user_code
    response = await _make_api_request("POST", "appointments/update/date", json_data=json_data)
    if response.get("success"):
        log_report_event("api_call", "System", "N/A", {"api": "update_appointment_date", "status": "success", "phone": phone, "appointment_id": appointment_id, "new_date": date})
    else:
        log_report_event("api_call", "System", "N/A", {"api": "update_appointment_date", "status": "failed", "error": response.get("message"), "phone": phone, "appointment_id": appointment_id})
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
    """Creates a new customer record within the clinic's database."""
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

    print(f"API Call: create_customer for name={name}, phone={phone_clean} (original: {phone}), gender={gender_api_format}, branch_id={branch_id}")
    json_data = {
        "name": name,
        "phone": phone_clean,
        "gender": gender_api_format  # Gender must be 'Male' or 'Female' as per API
    }
    if email: json_data["email"] = email
    # branch_id is required for create_customer
    if branch_id: json_data["branch_id"] = branch_id 
    if date_of_birth: json_data["date_of_birth"] = date_of_birth
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
