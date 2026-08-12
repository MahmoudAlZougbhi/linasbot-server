from __future__ import annotations

import datetime
import json
import os
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

import api_config

# No more telegram.Update or ContextTypes here
# from telegram import Update
# from telegram.ext import ContextTypes
import config

# NEW: Import Firestore utility functions

# Path to the daily reports log file
REPORT_LOG_FILE = "data/reports_log.jsonl"

# Increase timeout to 60 seconds for slow API endpoints (especially appointment queries)
api_client = httpx.AsyncClient(
    base_url=api_config.LINASLASER_API_BASE_URL or "",
    timeout=60.0,  # 60 seconds timeout instead of default 5 seconds
)


def _root_api_url(path: str) -> str:
    """Build an absolute URL at the API host root, outside /agent when needed."""
    base_url = str(api_config.LINASLASER_API_BASE_URL or "")
    parts = urlsplit(base_url)
    clean_path = "/" + str(path or "").lstrip("/")
    return str(urlunsplit((parts.scheme, parts.netloc, clean_path, "", "")))


def _normalize_update_status_endpoint(path: str) -> str:
    """
    Map LINASLASER_UPDATE_STATUS_PATH to the URL used by httpx.

    - ``/api/appointments/update-status`` or ``api/appointments/update-status`` → same host as
      LINASLASER_API_BASE_URL but path under site root (not under ``/agent/``).
    - Full ``http(s)://...`` → unchanged.
    - Anything else → agent-relative path (leading slashes stripped).
    """
    p = str(path or "").strip()
    if not p or p.lower() in ("off", "0", "false", "none"):
        return ""
    if p.lower().startswith(("http://", "https://")):
        return p
    if p.startswith("/") or p.startswith("api/"):
        return _root_api_url(p.lstrip("/"))
    return p.lstrip("/")


def _update_status_post_url_candidates() -> list[str]:
    """Ordered POST targets for CRM update-status; CRM lives at host ``/api/...``, not under ``/agent/``."""
    out: list[str] = []
    configured = (os.getenv("LINASLASER_UPDATE_STATUS_PATH") or "").strip()
    if configured:
        norm = _normalize_update_status_endpoint(configured)
        if norm:
            out.append(norm)
    for d in (
        # Some stacks expose update/status (slash) instead of update-status (hyphen).
        _root_api_url("api/appointments/update/status"),
        _root_api_url("api/appointments/update-status"),
        "api/appointments/update-status",
        "appointments/update-status",
    ):
        if d and d not in out:
            out.append(d)
    return out or [_root_api_url("api/appointments/update/status")]


_UPDATE_STATUS_LOG_BODY_MAX = 12000


async def _post_update_status_logged(resolved_url: str, json_data: dict) -> dict:
    """
    POST JSON to CRM update-status with full request/response logging (URL, method, payload, status, body).
    Normalizes CRM success when the body message is ``Status updated for X appointments``.
    """
    headers = {
        "Authorization": f"Bearer {api_config.LINASLASER_API_TOKEN}",
        "Content-Type": "application/json",
    }
    method = "POST"
    try:
        payload_preview = json.dumps(json_data, ensure_ascii=False)
    except (TypeError, ValueError):
        payload_preview = str(json_data)
    print(f"update_appointments_status HTTP {method} final_url={resolved_url} payload={payload_preview}")
    try:
        response = await api_client.post(resolved_url, json=json_data, headers=headers)
    except httpx.RequestError as e:
        print(f"update_appointments_status response status=(network_error) final_url={resolved_url} body={repr(e)}")
        return {
            "success": False,
            "message": f"Connection error (Network Error). {e!s}",
            "details": repr(e),
            "final_url": resolved_url,
            "http_method": method,
        }

    status_code = response.status_code
    body_text = response.text or ""
    body_log = body_text[:_UPDATE_STATUS_LOG_BODY_MAX]
    print(
        f"update_appointments_status response status={status_code} final_url={resolved_url} "
        f"body[:{_UPDATE_STATUS_LOG_BODY_MAX}]={body_log}"
    )

    base_meta = {"final_url": str(response.url), "http_method": method, "status_code": status_code}

    if status_code == 404:
        try:
            data = response.json()
            if isinstance(data, dict):
                merged = dict(data)
                merged.setdefault("success", False)
                merged.update(base_meta)
                return merged
        except json.JSONDecodeError:
            pass
        return {
            "success": False,
            "message": "API endpoint not found (404).",
            "status_code": 404,
            "raw_response": body_text[:500],
            **base_meta,
        }

    parsed: Any = None
    if body_text.strip():
        try:
            parsed = response.json()
        except json.JSONDecodeError:
            parsed = None

    if status_code >= 400:
        msg = None
        if isinstance(parsed, dict):
            msg = parsed.get("message") or parsed.get("error")
        msg = msg or body_text[:2000] or f"HTTP {status_code}"
        out = {
            "success": False,
            "message": f"Connection error (HTTP Error): {status_code}. Details: {msg}",
            "status_code": status_code,
            "raw_response": body_text[:2000],
            **base_meta,
        }
        if isinstance(parsed, dict):
            out["data"] = parsed
        return out

    # 2xx: normalize CRM success message
    ok = False
    message_str = ""
    if isinstance(parsed, dict):
        if parsed.get("success") is True:
            ok = True
        message_str = str(parsed.get("message", "") or "")
        if not ok and "status updated for" in message_str.lower():
            ok = True
    elif isinstance(parsed, str):
        message_str = parsed
        if "status updated for" in message_str.lower():
            ok = True

    if ok:
        out = dict(parsed) if isinstance(parsed, dict) else {"message": message_str or body_text.strip()}
        out["success"] = True
        out.update(base_meta)
        return out

    # 2xx with unexpected shape — treat as success if empty body (e.g. 204)
    if status_code in (200, 201, 204) and (parsed is None or parsed == {}):
        return {"success": True, "message": body_text.strip() or "ok", **base_meta}

    if isinstance(parsed, dict) and parsed.get("success") is False:
        out = dict(parsed)
        out.update(base_meta)
        return out

    out = dict(parsed) if isinstance(parsed, dict) else {"message": body_text.strip()[:500]}
    # 2xx JSON without explicit failure — treat as success (CRM may return shapes beyond the documented message).
    out["success"] = bool(isinstance(parsed, dict))
    out.update(base_meta)
    return out


async def _make_api_request(
    method: str, endpoint: str, params: dict | None = None, json_data: dict | None = None
) -> Any:
    """
    Helper function to make authenticated API requests to the LinasLaser Agent API.
    """
    headers = {"Authorization": f"Bearer {api_config.LINASLASER_API_TOKEN}", "Content-Type": "application/json"}

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
                return {
                    "success": False,
                    "message": f"API endpoint '{endpoint}' not found on server.",
                    "status_code": 404,
                    "raw_response": response.text,
                }

        response.raise_for_status()  # Raise an exception for other HTTP errors (4xx or 5xx except 404)
        return response.json()
    except httpx.HTTPStatusError as e:
        print(f"API HTTP Error for {endpoint}: {e.response.status_code} - {e.response.text}")
        return {
            "success": False,
            "message": f"Connection error (HTTP Error): {e.response.status_code}. Details: {e.response.text}",
            "status_code": e.response.status_code,
        }
    except httpx.RequestError as e:
        print(f"API Request Error for {endpoint}: {e}")
        print(f"  Error Type: {type(e).__name__}")
        print(f"  Error Details: {repr(e)}")
        return {
            "success": False,
            "message": "Connection error (Network Error). Please check internet connection.",
            "details": str(e),
        }
    except json.JSONDecodeError as e:
        raw = (getattr(response, "text", None) or str(e))[:500]
        print(f"API JSON Decode Error for {endpoint}: {e} - Response: {raw}")
        return {
            "success": False,
            "message": "Error processing system response. Invalid JSON from API.",
            "details": str(e),
            "raw_response": raw,
        }
    except Exception as e:
        print(f"Unexpected API Error for {endpoint}: {e}")
        return {
            "success": False,
            "message": f"An unexpected error occurred while connecting to the system: {str(e)}",
            "details": str(e),
        }


# Modified log_report_event to accept user_id and update Firestore metrics
def log_report_event(event_type: str, user_id: str, user_gender: str, details: dict | None = None) -> None:
    user_name = config.user_names.get(user_id, "N/A")  # Get user_name from config
    event_data = {
        "timestamp": datetime.datetime.now().isoformat(),
        "type": event_type,
        "user_id": user_id,  # Log user_id for better tracking
        "user_name": user_name,
        "user_gender": user_gender,
        "details": details if details else {},
    }
    try:
        os.makedirs("data", exist_ok=True)
        with open(REPORT_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(event_data, ensure_ascii=False) + "\n")
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
        pass  # No direct Firestore update here to avoid async issues in a sync function

    except Exception as e:
        print(f"❌ ERROR logging report event: {e}")
