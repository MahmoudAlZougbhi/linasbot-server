"""Customer create/gender and daily report generation (LOC split)."""

from __future__ import annotations

import datetime
import json
import os
from typing import Any

import config
from services.api_integrations_http import REPORT_LOG_FILE, _make_api_request, log_report_event


async def check_customer_gender(phone: str | None = None, user_code: str | None = None) -> Any:
    """Returns the gender of a customer based on the provided identifier."""
    # Clean phone number to match API expected format (without + prefix and country code)
    phone_clean = None
    if phone:
        phone_clean = str(phone).replace("+", "").replace(" ", "").replace("-", "")
        if phone_clean.startswith("961"):
            phone_clean = phone_clean[3:]  # Remove Lebanon country code

    print(f"API Call: check_customer_gender for phone=***{str(phone_clean)[-4:] if phone_clean else ''} (original_last4=***{str(phone)[-4:] if phone else ''}), user_code={user_code}")
    params = {}
    # NEW: Ensure either phone or user_code is provided for the API call
    if phone_clean:
        params["phone"] = phone_clean
    elif user_code:  # Prioritize user_code if phone is not provided and user_code is.
        params["user_code"] = user_code
    else:  # If neither is provided, return an error as per API docs
        return {"success": False, "message": "Either phone or user_code must be provided."}

    response = await _make_api_request("GET", "customers/gender", params=params)
    if response.get("success"):  # Check if the API itself returned success
        log_report_event(
            "api_call",
            "System",
            "N/A",
            {
                "api": "check_customer_gender",
                "status": "success",
                "phone": phone,
                "gender": response.get("data", {}).get("gender"),
            },
        )
    else:  # API returned success:false or a non-200 status (other than 404 handled above)
        log_report_event(
            "api_call",
            "System",
            "N/A",
            {"api": "check_customer_gender", "status": "failed", "error": response.get("message"), "phone": phone},
        )
    return response


async def create_customer(
    name: str,
    phone: str,
    gender: str,
    email: str | None = None,
    branch_id: int | None = None,
    date_of_birth: str | None = None,
) -> Any:
    """Creates a new customer record within the clinic's database (POST customers/create).

    `branch_id` is required by the Agent API; callers may omit it only to mean
    `config.DEFAULT_BRANCH_ID`. If no valid branch can be resolved, the HTTP
    request is not sent.
    """
    # Resolve branch: explicit arg wins, else clinic default from config
    resolved_branch = branch_id if branch_id is not None else getattr(config, "DEFAULT_BRANCH_ID", None)
    resolved_branch_int: int | None
    if resolved_branch is None:
        resolved_branch_int = None
    else:
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
                        print(
                            f"⚠️ create_customer: Detected invalid phone=***{str(phone)[-4:] if phone else ''}, using actual phone ***{str(data['phone_number'])[-4:]}"
                        )
                        phone_clean = str(data["phone_number"]).replace("+", "").replace(" ", "").replace("-", "")
                        if phone_clean.startswith("961"):
                            phone_clean = phone_clean[3:]
                        break

    # Convert gender to API format: "male"/"female" -> "Male"/"Female"
    gender_api_format = gender.capitalize() if gender.lower() in ["male", "female"] else "Male"

    print(
        f"API Call: create_customer for name_len={len(str(name or ''))}, phone=***{str(phone_clean)[-4:] if phone_clean else ''} (original_last4=***{str(phone)[-4:] if phone else ''}), "
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
        log_report_event(
            "api_call",
            "System",
            "N/A",
            {"api": "create_customer", "status": "success", "phone": phone, "customer": response.get("data")},
        )
    else:
        log_report_event(
            "api_call",
            "System",
            "N/A",
            {"api": "create_customer", "status": "failed", "error": response.get("message"), "phone": phone},
        )
    return response


async def update_customer_gender(customer_id: int, gender: str) -> Any:
    """
    DEPRECATED: The external API does not support updating customer gender (returns 404).
    Gender is now persisted via Firestore in user_persistence_service.py.
    This function is kept for backwards compatibility but will always fail.
    Use user_persistence.save_user_gender() instead.
    """
    print(f"⚠️ DEPRECATED: update_customer_gender called for customer_id={customer_id}, gender={gender}")
    print("⚠️ External API does not support gender updates. Use Firestore via user_persistence.save_user_gender()")

    # Return a mock success to prevent errors in legacy code
    # Gender is actually saved via Firestore in user_persistence_service.py
    return {"success": True, "message": "Gender saved via Firestore (external API deprecated)"}



# Refactored generate_daily_report_command to return string and accept send_message_func
async def generate_daily_report_command(user_id: str, send_message_func: Any) -> Any:
    """
    Generates a daily report of bot interactions and returns it as a string.
    This function is now platform-agnostic and relies on send_message_func to send the report.
    """
    if user_id != config.TRAINER_WHATSAPP_NUMBER:  # Use WhatsApp number for trainer ID check
        await send_message_func(user_id, "ليس لديك صلاحية لطلب التقرير اليومي.")
        return ""  # Return empty string if not authorized

    # The calling function (in main.py or handlers) already sends "جارٍ توليد التقرير اليومي..."
    # So we don't send it here.

    report_data: dict[str, Any] = {
        "new_users": {"male": 0, "female": 0, "unspecified": 0},
        "appointments_booked": {"male": 0, "female": 0, "unspecified": 0, "details": []},
        "appointments_rescheduled": {"male": 0, "female": 0, "unspecified": 0, "details": []},
        "complaints": {"male": 0, "female": 0, "unspecified": 0, "details": []},
        "burn_reports": {"male": 0, "female": 0, "unspecified": 0, "details": []},
        "human_handover_requests": {"male": 0, "female": 0, "unspecified": 0, "details": []},
        "missed_appointments": {"male": 0, "female": 0, "unspecified": 0, "details": []},
        "total_interactions": 0,
        "api_calls": {"success": 0, "failed": 0, "details": []},
    }

    today_str = datetime.date.today().isoformat()
    try:
        if os.path.exists(REPORT_LOG_FILE):
            with open(REPORT_LOG_FILE, encoding="utf-8") as f:
                for line in f:
                    try:
                        event = json.loads(line)
                        if event["timestamp"].startswith(today_str):
                            report_data["total_interactions"] += 1
                            user_gender = event.get("user_gender", "unspecified")
                            event_type = event["type"]
                            event_user_name = event.get("user_name", "N/A")  # Get name from event log

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
                                if event["details"].get("status") == "success":
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

    appointments_booked_details_str = (
        "\n  ".join(report_data["appointments_booked"]["details"])
        if report_data["appointments_booked"]["details"]
        else "N/A"
    )
    appointments_rescheduled_details_str = (
        "\n  ".join(report_data["appointments_rescheduled"]["details"])
        if report_data["appointments_rescheduled"]["details"]
        else "N/A"
    )
    human_handover_requests_details_str = (
        "\n  ".join(report_data["human_handover_requests"]["details"])
        if report_data["human_handover_requests"]["details"]
        else "N/A"
    )
    burn_reports_details_str = (
        "\n  ".join(report_data["burn_reports"]["details"]) if report_data["burn_reports"]["details"] else "N/A"
    )
    missed_appointments_details_str = (
        "\n  ".join(report_data["missed_appointments"]["details"])
        if report_data["missed_appointments"]["details"]
        else "N/A"
    )
    complaints_details_str = (
        "\n  ".join(report_data["complaints"]["details"]) if report_data["complaints"]["details"] else "N/A"
    )
    api_calls_details_str = (
        "\n  ".join(report_data["api_calls"]["details"]) if report_data["api_calls"]["details"] else "N/A"
    )

    report_message = (
        f"📊 *Daily Bot Report - {today_str}*\n"  # Using * for bold as WhatsApp might not support **
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
    return report_message  # Return the message instead of sending directly
