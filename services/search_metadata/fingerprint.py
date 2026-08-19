"""Content fingerprints excluding generated search metadata."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from services.search_metadata.limits import META_FIELD_KEYS


def strip_meta_fields(item: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in dict(item or {}).items() if k not in META_FIELD_KEYS}


def content_fingerprint(item: dict[str, Any] | None) -> str:
    payload = strip_meta_fields(item or {})
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def item_id_of(item: dict[str, Any]) -> str:
    return str(item.get("id") or item.get("qa_group_id") or "").strip()
