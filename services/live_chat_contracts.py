"""Canonical contracts and normalization helpers for Live Chat."""

from __future__ import annotations

import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple


UTC = datetime.timezone.utc
SOURCE_MESSAGE_ID_KEYS = (
    "source_message_id",
    "message_id",
    "webhook_message_id",
    "wamid",
)


def utc_now() -> datetime.datetime:
    """Return timezone-aware current timestamp in UTC."""
    return datetime.datetime.now(UTC)


def parse_timestamp_utc(
    timestamp: Any,
    *,
    fallback: Optional[datetime.datetime] = None,
) -> datetime.datetime:
    """Parse mixed timestamp values into UTC-aware datetimes."""
    fallback_ts = fallback or utc_now()

    if timestamp is None:
        return fallback_ts

    if isinstance(timestamp, datetime.datetime):
        dt = timestamp
    elif isinstance(timestamp, str):
        try:
            dt = datetime.datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except Exception:
            return fallback_ts
    elif isinstance(timestamp, (int, float)):
        seconds = timestamp / 1000.0 if timestamp >= 1e12 else float(timestamp)
        return datetime.datetime.fromtimestamp(seconds, tz=UTC)
    elif hasattr(timestamp, "timestamp"):
        try:
            return datetime.datetime.fromtimestamp(timestamp.timestamp(), tz=UTC)
        except Exception:
            return fallback_ts
    elif hasattr(timestamp, "seconds"):
        try:
            return datetime.datetime.fromtimestamp(timestamp.seconds, tz=UTC)
        except Exception:
            return fallback_ts
    else:
        return fallback_ts

    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def isoformat_utc(timestamp: Any, *, fallback: Optional[datetime.datetime] = None) -> str:
    """Return ISO8601 string for a mixed timestamp value."""
    return parse_timestamp_utc(timestamp, fallback=fallback).isoformat()


def extract_source_message_id(metadata: Any) -> str:
    """Extract canonical source message id from metadata."""
    if not isinstance(metadata, dict):
        return ""
    for key in SOURCE_MESSAGE_ID_KEYS:
        value = metadata.get(key)
        if value:
            return str(value).strip()
    return ""


def normalize_message_metadata(metadata: Any) -> Dict[str, Any]:
    """Normalize metadata and preserve canonical source id field."""
    normalized = dict(metadata or {}) if isinstance(metadata, dict) else {}
    source_message_id = extract_source_message_id(normalized)
    if source_message_id:
        normalized["source_message_id"] = source_message_id
    return normalized


def normalize_message(message: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize one message payload while preserving backward compatibility."""
    payload = dict(message or {})
    metadata = normalize_message_metadata(payload.get("metadata"))

    role = str(payload.get("role", "")).strip().lower() or "user"
    text = payload.get("text", "")
    safe_text = text if isinstance(text, str) else str(text or "")
    timestamp = parse_timestamp_utc(payload.get("timestamp"))

    msg_type = str(payload.get("type") or metadata.get("type") or "text").strip().lower() or "text"

    normalized: Dict[str, Any] = {
        "role": role,
        "text": safe_text,
        "timestamp": timestamp,
        "type": msg_type,
    }

    if payload.get("language"):
        normalized["language"] = payload.get("language")
    if metadata:
        normalized["metadata"] = metadata

    for media_key in ("audio_url", "image_url"):
        media_value = payload.get(media_key) or metadata.get(media_key)
        if media_value:
            normalized[media_key] = media_value

    for passthrough_key in ("handled_by", "transcribed", "transcribed_at", "message_id"):
        if passthrough_key in payload:
            normalized[passthrough_key] = payload[passthrough_key]
    if "message_id" not in normalized and metadata.get("message_id"):
        normalized["message_id"] = metadata["message_id"]
    if "message_id" not in normalized and metadata.get("source_message_id"):
        normalized["message_id"] = metadata["source_message_id"]

    return normalized


def _build_message_signature(message: Dict[str, Any]) -> Tuple[str, str, str, str]:
    metadata = message.get("metadata", {}) or {}
    role = str(message.get("role", "")).strip().lower()
    msg_type = str(message.get("type") or metadata.get("type") or "text").strip().lower()
    text = str(message.get("text", "")).strip()
    timestamp = parse_timestamp_utc(message.get("timestamp")).replace(microsecond=0).isoformat()
    return role, msg_type, text, timestamp


def is_duplicate_message(
    existing_messages: Iterable[Dict[str, Any]],
    new_message: Dict[str, Any],
    *,
    dedupe_window_seconds: int = 20,
) -> bool:
    """Shared duplicate-detection rule for save/read consistency."""
    existing = list(existing_messages or [])
    if not existing:
        return False

    normalized_new = normalize_message(new_message)
    new_source_id = extract_source_message_id(normalized_new.get("metadata", {}) or {})
    if new_source_id:
        for existing_msg in reversed(existing[-100:]):
            existing_source_id = extract_source_message_id((existing_msg or {}).get("metadata", {}) or {})
            if existing_source_id and existing_source_id == new_source_id:
                return True

    new_role = str(normalized_new.get("role", "")).strip().lower()
    if new_role != "user":
        return False

    new_signature = _build_message_signature(normalized_new)
    new_ts = parse_timestamp_utc(normalized_new.get("timestamp"))
    for existing_msg in reversed(existing[-20:]):
        normalized_existing = normalize_message(existing_msg or {})
        existing_signature = _build_message_signature(normalized_existing)
        if existing_signature[:3] != new_signature[:3]:
            continue
        existing_ts = parse_timestamp_utc(normalized_existing.get("timestamp"))
        if abs((new_ts - existing_ts).total_seconds()) <= dedupe_window_seconds:
            return True

    return False


def dedupe_messages(messages: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Stable message dedupe used by all read paths."""
    deduped: List[Dict[str, Any]] = []
    seen_source_ids = set()
    seen_signatures = set()

    for raw_message in list(messages or []):
        message = normalize_message(raw_message or {})
        message_id = message.get("message_id") or extract_source_message_id(message.get("metadata", {}) or {})
        if message_id:
            if message_id in seen_source_ids:
                continue
            seen_source_ids.add(message_id)

        signature = _build_message_signature(message)
        if not message_id and signature in seen_signatures:
            continue

        seen_signatures.add(signature)
        deduped.append(message)

    return deduped


def normalize_conversation_document(
    conversation_id: str,
    user_id: str,
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    """Normalize a raw conversation document while keeping contract fields."""
    data = dict(payload or {})
    normalized_messages = dedupe_messages(data.get("messages", []))
    return {
        "conversation_id": conversation_id,
        "user_id": str(data.get("user_id") or user_id),
        "customer_info": dict(data.get("customer_info", {}) or {}),
        "messages": normalized_messages,
        "timestamp": parse_timestamp_utc(data.get("timestamp")),
        "last_updated": parse_timestamp_utc(data.get("last_updated")),
        "status": str(data.get("status") or "active"),
        "sentiment": str(data.get("sentiment") or "neutral"),
        "human_takeover_active": bool(data.get("human_takeover_active", False)),
        "operator_id": data.get("operator_id"),
        "operator_name": data.get("operator_name"),
    }
