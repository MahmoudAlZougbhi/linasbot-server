"""Phone/room identity helpers (Qiscus room_id vs phone canonicalization)."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from utils.phone_utils import is_phone_like_user_id, normalize_phone

_log = logging.getLogger(__name__)


_PHONE_ROOM_MAPPING_CACHE: dict[str, Any] = {"mtime": None, "room_to_phone": {}}


def get_canonical_user_id_and_phone(user_id: str, phone_number: str | None = None) -> tuple[str, str | None]:
    """
    Return (canonical_user_id, normalized_phone) for Firestore and identity.
    - If we have a real phone (from phone_number or user_id when phone-like), canonical_user_id = normalized_phone (E.164).
    - Otherwise canonical_user_id = user_id (e.g. room_id). normalized_phone may be "".
    """
    raw_phone = phone_number or (user_id if is_phone_like_user_id(user_id) else None)
    if not raw_phone or str(raw_phone).strip().startswith("room:"):
        mapped = _resolve_phone_from_room_mapping(user_id)
        raw_phone = mapped or None
    normalized = normalize_phone(raw_phone) if raw_phone else ""
    canonical = normalized if normalized else user_id
    return canonical, normalized


def _normalize_phone_digits(value: str) -> str:
    if value is None:
        return ""
    digits = re.sub(r"\D", "", str(value))
    if digits.startswith("00"):
        digits = digits[2:]
    return digits


def _is_placeholder_phone(phone_number: Any) -> bool:
    if phone_number is None:
        return True
    if not isinstance(phone_number, str):
        if isinstance(phone_number, (int, float)):
            phone_number = str(phone_number)
        else:
            return True
    value = str(phone_number).strip().lower()
    return (not value) or value in {"unknown", "none", "null"} or value.startswith("room:")


def _clean_phone_for_lookup(phone_number: str) -> str:
    digits = _normalize_phone_digits(phone_number)
    if digits.startswith("961") and len(digits) > 8:
        return digits[3:]
    if digits.startswith("1") and len(digits) == 11:
        return digits[1:]
    return digits


def _load_room_to_phone_mapping() -> dict[str, str]:
    """
    Load room_id -> phone mapping from data/phone_to_room_mapping.json with mtime cache.
    """
    mapping_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "data",
        "phone_to_room_mapping.json",
    )

    try:
        mtime = os.path.getmtime(mapping_path)
    except Exception:
        _PHONE_ROOM_MAPPING_CACHE["room_to_phone"] = {}
        _PHONE_ROOM_MAPPING_CACHE["mtime"] = None
        return {}

    if _PHONE_ROOM_MAPPING_CACHE["mtime"] == mtime:
        cached = _PHONE_ROOM_MAPPING_CACHE["room_to_phone"]
        return dict(cached) if isinstance(cached, dict) else {}

    room_to_phone = {}
    try:
        with open(mapping_path, encoding="utf-8") as mapping_file:
            mapping_data = json.load(mapping_file) or {}

        raw_phone_to_room = mapping_data.get("phone_to_room_mapping", {})
        if isinstance(raw_phone_to_room, dict):
            for raw_phone, raw_room_id in raw_phone_to_room.items():
                room_id = str(raw_room_id).strip()
                phone_value = str(raw_phone).strip()
                if room_id and phone_value:
                    room_to_phone[room_id] = phone_value

        raw_room_to_phone = mapping_data.get("room_to_phone_mapping", {})
        if isinstance(raw_room_to_phone, dict):
            for raw_room_id, raw_phone in raw_room_to_phone.items():
                room_id = str(raw_room_id).strip()
                phone_value = str(raw_phone).strip()
                if room_id and phone_value:
                    room_to_phone[room_id] = phone_value
    except Exception as e:
        print(f"⚠️ Failed loading phone_to_room_mapping.json: {e}")
        room_to_phone = {}

    _PHONE_ROOM_MAPPING_CACHE["room_to_phone"] = room_to_phone
    _PHONE_ROOM_MAPPING_CACHE["mtime"] = mtime
    return room_to_phone


def _resolve_phone_from_room_mapping(user_id: str) -> str:
    room_to_phone = _load_room_to_phone_mapping()
    return room_to_phone.get(str(user_id).strip(), "")


def persist_room_to_phone_mapping(room_id: str, phone: str) -> None:
    """
    Persist room_id -> phone to data/phone_to_room_mapping.json so future requests
    with room_id (e.g. from Qiscus) resolve to the same canonical user. Prevents
    duplicate conversations when provider sends room_id instead of phone.
    """
    if not room_id or not phone or str(phone).strip().startswith("room:"):
        return
    room_id = str(room_id).strip()
    phone = str(phone).strip()
    if not room_id or not phone:
        return
    mapping_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "data",
        "phone_to_room_mapping.json",
    )
    try:
        data: dict[str, Any] = {}
        if os.path.exists(mapping_path):
            with open(mapping_path, encoding="utf-8") as f:
                data = json.load(f) or {}
        phone_to_room = dict(data.get("phone_to_room_mapping") or {})
        room_to_phone = dict(data.get("room_to_phone_mapping") or {})
        if phone_to_room.get(phone) == room_id and room_to_phone.get(room_id) == phone:
            return
        phone_to_room[phone] = room_id
        room_to_phone[room_id] = phone
        data["phone_to_room_mapping"] = phone_to_room
        data["room_to_phone_mapping"] = room_to_phone
        data.setdefault("notes", "Auto-persisted room<->phone for identity deduplication")
        os.makedirs(os.path.dirname(mapping_path), exist_ok=True)
        with open(mapping_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        _PHONE_ROOM_MAPPING_CACHE["mtime"] = None
        _log.info("Persisted room_to_phone room_id=%s phone=%s", room_id, phone)
    except Exception as e:
        _log.warning("Failed to persist room_to_phone mapping: %s", e)
