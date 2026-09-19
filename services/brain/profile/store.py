"""Stable customer profile fields. Store only keys the active request graph requires."""

from __future__ import annotations

import threading
from typing import Any

PROFILE_KEYS = ("name", "gender", "age", "phone")
_ALIASES = {
    "name": "name",
    "customer_name": "name",
    "full_name": "name",
    "gender": "gender",
    "age": "age",
    "phone": "phone",
    "mobile": "phone",
}

_LOCK = threading.Lock()
_MEMORY: dict[str, dict[str, str]] = {}


def reset_profile_store_for_tests() -> None:
    with _LOCK:
        _MEMORY.clear()


def _scope(tenant_id: str, customer_id: str, conversation_id: str = "") -> str:
    who = (customer_id or conversation_id or "anon").strip()
    return f"{(tenant_id or '').strip()}::{who}"


def profile_key(raw: str) -> str | None:
    token = (raw or "").strip().casefold()
    return _ALIASES.get(token)


def filter_required(fields: dict[str, Any], required: set[str]) -> dict[str, str]:
    allowed = {key for key in (profile_key(item) or "" for item in required) if key in PROFILE_KEYS}
    out: dict[str, str] = {}
    for raw, value in (fields or {}).items():
        key = profile_key(str(raw))
        text = str(value or "").strip()
        if key in allowed and text:
            out[key] = text[:120]
    return out


def remember_profile(
    tenant_id: str,
    customer_id: str,
    fields: dict[str, Any],
    *,
    required: set[str],
    conversation_id: str = "",
) -> dict[str, str]:
    stored = filter_required(fields, required)
    if not stored or not (tenant_id or "").strip():
        return {}
    scope = _scope(tenant_id, customer_id, conversation_id)
    with _LOCK:
        bucket = dict(_MEMORY.get(scope) or {})
        bucket.update(stored)
        _MEMORY[scope] = bucket
        return dict(bucket)


def recall_profile(tenant_id: str, customer_id: str, *, conversation_id: str = "") -> dict[str, str]:
    if not (tenant_id or "").strip():
        return {}
    scope = _scope(tenant_id, customer_id, conversation_id)
    with _LOCK:
        return dict(_MEMORY.get(scope) or {})


def confirm_candidates(profile: dict[str, str], required: set[str]) -> dict[str, str]:
    allowed = {key for key in (profile_key(item) or "" for item in required) if key in PROFILE_KEYS}
    return {key: value for key, value in profile.items() if key in allowed and value}
