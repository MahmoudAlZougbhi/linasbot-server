"""Clinic catalog API (branches, services, machines, body parts, hours)."""

from __future__ import annotations

import os
from typing import Any

from services.api_integrations_http import _make_api_request, log_report_event


async def get_branches() -> Any:
    """Retrieves a list of all branches associated with the clinic."""
    print("API Call: get_branches")
    response = await _make_api_request("GET", "branches")
    if response.get("success"):
        log_report_event(
            "api_call",
            "System",
            "N/A",
            {"api": "get_branches", "status": "success", "count": len(response.get("data", []))},
        )
    else:
        log_report_event(
            "api_call", "System", "N/A", {"api": "get_branches", "status": "failed", "error": response.get("message")}
        )
    return response


async def get_services() -> Any:
    """Retrieves a list of all services offered by the clinic."""
    print("API Call: get_services")
    response = await _make_api_request("GET", "services")
    if response.get("success"):
        log_report_event(
            "api_call",
            "System",
            "N/A",
            {"api": "get_services", "status": "success", "count": len(response.get("data", []))},
        )
    else:
        log_report_event(
            "api_call", "System", "N/A", {"api": "get_services", "status": "failed", "error": response.get("message")}
        )
    return response


async def get_machines() -> Any:
    """Retrieves a list of all machines available in the clinic."""
    print("API Call: get_machines")
    response = await _make_api_request("GET", "machines")
    if response.get("success"):
        log_report_event(
            "api_call",
            "System",
            "N/A",
            {"api": "get_machines", "status": "success", "count": len(response.get("data", []))},
        )
    else:
        log_report_event(
            "api_call", "System", "N/A", {"api": "get_machines", "status": "failed", "error": response.get("message")}
        )
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


def _row_looks_like_body_part(entry: Any) -> bool:
    if not isinstance(entry, dict):
        return False
    return entry.get("id") is not None or entry.get("body_part_id") is not None


def _coerce_body_parts_list(raw: Any) -> list | None:
    """Return a list if raw is a non-empty list of body-part-like dicts, or an empty list if explicitly empty."""
    if not isinstance(raw, list):
        return None
    if len(raw) == 0:
        return []
    if all(_row_looks_like_body_part(x) for x in raw):
        return raw
    return None


def _extract_body_parts_from_service_data_response(sd: dict) -> list | None:
    """
    GET service/data carries pricing + body area rows (BOC Appointment API). Same rows may appear under
    data.body_parts, areas, body_areas, top-level body_parts, or nested (e.g. under service / pricing).
    """
    if not isinstance(sd, dict) or not sd.get("success"):
        return None
    for key in ("body_parts", "areas", "body_areas"):
        if key in sd:
            got = _coerce_body_parts_list(sd[key])
            if got is not None:
                return got
    d = sd.get("data")
    if d is None:
        return None
    if isinstance(d, list):
        return _coerce_body_parts_list(d)
    if not isinstance(d, dict):
        return None
    for key in ("body_parts", "areas", "body_areas", "zones", "locations", "parts"):
        if key not in d:
            continue
        got = _coerce_body_parts_list(d[key])
        if got is not None:
            return got
    for nest_key in ("service", "pricing", "details", "options"):
        nested = d.get(nest_key)
        if not isinstance(nested, dict):
            continue
        for key in ("body_parts", "areas", "body_areas"):
            if key not in nested:
                continue
            got = _coerce_body_parts_list(nested[key])
            if got is not None:
                return got
    for v in d.values():
        got = _coerce_body_parts_list(v)
        if got is not None:
            return got
    return None


def _deep_scan_body_parts(obj: Any, depth: int = 0) -> list | None:
    """Find a body-part row list anywhere in a successful service/data JSON (odd CRM nesting)."""
    if depth > 8 or obj is None:
        return None
    got = _coerce_body_parts_list(obj)
    if got is not None:
        return got
    if isinstance(obj, dict):
        for k in ("body_parts", "areas", "body_areas", "zones", "locations", "parts"):
            if k not in obj:
                continue
            got = _coerce_body_parts_list(obj[k])
            if got is not None:
                return got
        for v in obj.values():
            found = _deep_scan_body_parts(v, depth + 1)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = _deep_scan_body_parts(item, depth + 1)
            if found is not None:
                return found
    return None


def _service_data_shape_hint(sd: dict) -> Any:
    d = sd.get("data") if isinstance(sd, dict) else None
    if isinstance(d, dict):
        return {"data_keys": list(d.keys())[:40]}
    if isinstance(d, list):
        return {"data": "list", "len": len(d)}
    return {"data_type": type(d).__name__}


async def get_body_parts(service_id: int | None = None, machine_id: int | None = None) -> Any:
    """Returns list of body parts (id, name) for pricing/booking.  service_id/machine_id filters."""
    print("API Call: get_body_parts")
    params = {}
    if service_id is not None:
        params["service_id"] = service_id
    if machine_id is not None:
        params["machine_id"] = machine_id
    q = params if params else None
    last: dict = {"success": False, "message": "get_body_parts: no endpoint tried"}

    def _log_body_parts_success(path: str, count: int) -> None:
        log_report_event(
            "api_call",
            "System",
            "N/A",
            {
                "api": "get_body_parts",
                "path": path,
                "status": "success",
                "count": count,
                "service_id": service_id,
                "machine_id": machine_id,
            },
        )

    custom = (os.getenv("LINASLASER_GET_BODY_PARTS_PATH") or "").strip().lstrip("/")
    if custom:
        response = await _make_api_request("GET", custom, params=q)
        last = response
        if response.get("success"):
            rows = response.get("data")
            n = len(rows) if isinstance(rows, list) else 0
            _log_body_parts_success(custom, n)
            return response
        msg = str(response.get("message") or "").lower()
        sc = response.get("status_code")
        if sc != 404 and "not found" not in msg:
            log_report_event(
                "api_call",
                "System",
                "N/A",
                {
                    "api": "get_body_parts",
                    "path": custom,
                    "status": "failed",
                    "error": response.get("message"),
                    "service_id": service_id,
                    "machine_id": machine_id,
                },
            )
            return response
        print(f"API Call: get_body_parts — {custom} failed, continuing")

    # BOC Appointment API: areas + price come from GET service/data (there is no GET body_parts in the official doc).
    if service_id is not None:
        sd = await get_service_data(int(service_id), machine_id)
        last = sd
        parts = _extract_body_parts_from_service_data_response(sd)
        if parts is None:
            parts = _deep_scan_body_parts(sd)
        if parts is not None:
            out = {"success": True, "data": parts}
            _log_body_parts_success("service/data", len(parts))
            return out
        if sd.get("success"):
            err = {
                "success": False,
                "message": (
                    "GET service/data succeeded but no body_parts rows were found in the JSON. "
                    "Trying legacy body-parts endpoints next; if they also fail, confirm the CRM exposes body_parts "
                    "(or areas) under data per Appointment API."
                ),
                "service_data_shape": _service_data_shape_hint(sd),
            }
            last = err
            log_report_event(
                "api_call",
                "System",
                "N/A",
                {
                    "api": "get_body_parts",
                    "path": "service/data",
                    "status": "failed",
                    "error": err["message"],
                    "service_id": service_id,
                    "machine_id": machine_id,
                    "hint": _service_data_shape_hint(sd),
                },
            )
            print("API Call: get_body_parts — service/data had no rows, trying legacy GET paths")
        msg = str(sd.get("message") or "").lower()
        sc = sd.get("status_code")
        if sc not in (404, None) and "not found" not in msg:
            log_report_event(
                "api_call",
                "System",
                "N/A",
                {
                    "api": "get_body_parts",
                    "path": "service/data",
                    "status": "failed",
                    "error": sd.get("message"),
                    "service_id": service_id,
                    "machine_id": machine_id,
                },
            )
            return sd
        print("API Call: get_body_parts — service/data unavailable (404), trying legacy GET paths")

    for ep in _body_part_endpoint_candidates():
        if ep == custom:
            continue
        response = await _make_api_request("GET", ep, params=q)
        last = response
        if response.get("success"):
            rows = response.get("data")
            n = len(rows) if isinstance(rows, list) else 0
            _log_body_parts_success(ep, n)
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


async def get_service_data(service_id: int, machine_id: int | None = None) -> Any:
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


async def get_clinic_hours() -> Any:
    """Returns the clinic's working hours for each day of the week."""
    print("API Call: get_clinic_hours")
    response = await _make_api_request("GET", "clinic/hours")
    if response.get("success"):
        log_report_event(
            "api_call", "System", "N/A", {"api": "get_clinic_hours", "status": "success", "data": response.get("data")}
        )
    else:
        log_report_event(
            "api_call",
            "System",
            "N/A",
            {"api": "get_clinic_hours", "status": "failed", "error": response.get("message")},
        )
    return response
