"""Shared appointment payload helpers used outside the removed classic GPT engine."""

from __future__ import annotations


def extract_customer_appointments_list(response_payload: dict) -> list:
    """Normalize get_customer_appointments API payload to a list of appointment dicts."""
    if not isinstance(response_payload, dict):
        return []
    data = response_payload.get("data")
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        if isinstance(data.get("appointments"), list):
            return [item for item in data.get("appointments", []) if isinstance(item, dict)]
        if isinstance(data.get("data"), list):
            return [item for item in data.get("data", []) if isinstance(item, dict)]
        appointment_payload = data.get("appointment")
        if isinstance(appointment_payload, dict):
            return [appointment_payload]
        for key in ("appointment_id", "id", "appointmentId"):
            if data.get(key) is not None:
                return [data]
    return []


def is_placeholder_booking_customer_name(name: str | None) -> bool:
    if not name or not str(name).strip():
        return True
    n = str(name).strip().lower()
    placeholders = {
        "client",
        "unknown",
        "unknown customer",
        "instagram customer",
        "facebook customer",
        "test user",
        "guest",
        "user",
        "customer",
        "new user",
        "anonymous",
        "not known",
        "n/a",
        "na",
    }
    if n in placeholders:
        return True
    if n.startswith("test user"):
        return True
    return False


# Historical names used by campaign + display-name tests.
_extract_customer_appointments_list = extract_customer_appointments_list
_is_placeholder_booking_customer_name = is_placeholder_booking_customer_name
