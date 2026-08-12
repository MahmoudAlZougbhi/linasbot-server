"""Template JSON store helpers for smart messaging API (LOC split)."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from collections.abc import Iterator
from typing import Any

from services.smart_messaging_catalog import (
    CAMPAIGN_TEMPLATE_IDS,
    DAILY_TEMPLATE_IDS,
    DEPRECATED_TEMPLATE_IDS,
    TEMPLATE_METADATA,
    normalize_template_id,
)
from storage.persistent_storage import (
    MESSAGE_TEMPLATES_FILE,
    MESSAGE_TEMPLATES_LOCK_FILE,
    SMART_MESSAGING_DIR,
    ensure_dirs,
)

_fcntl_mod: Any
try:
    import fcntl as _fcntl_mod
except ImportError:
    _fcntl_mod = None

fcntl: Any = _fcntl_mod

_TEMPLATE_FILE = MESSAGE_TEMPLATES_FILE
_TEMPLATE_LOCK_FILE = MESSAGE_TEMPLATES_LOCK_FILE
_PROCESS_TEMPLATE_LOCK = threading.Lock()


def _template_store_lock() -> Iterator[None]:
    """Lock template read/write across threads and (on Unix) processes."""
    ensure_dirs()
    with _PROCESS_TEMPLATE_LOCK:
        with open(_TEMPLATE_LOCK_FILE, "a+", encoding="utf-8") as lock_handle:
            if fcntl is not None:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                if fcntl is not None:
                    fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)


def _load_templates_from_disk() -> dict[str, Any]:
    if not _TEMPLATE_FILE.exists():
        return {}

    with open(_TEMPLATE_FILE, encoding="utf-8") as f:
        templates = json.load(f)

    if not isinstance(templates, dict):
        raise ValueError("Invalid templates file format: expected JSON object")

    return templates


def _save_templates_to_disk(templates: dict[str, Any]) -> None:
    ensure_dirs()
    temp_fd, temp_path = tempfile.mkstemp(dir=str(SMART_MESSAGING_DIR), prefix="message_templates_", suffix=".json")

    try:
        with os.fdopen(temp_fd, "w", encoding="utf-8") as temp_file:
            json.dump(templates, temp_file, ensure_ascii=False, indent=2)
            temp_file.flush()
            os.fsync(temp_file.fileno())

        os.replace(temp_path, _TEMPLATE_FILE)
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass


def _default_template_ids() -> list[str]:
    return list(DAILY_TEMPLATE_IDS) + list(CAMPAIGN_TEMPLATE_IDS)


def _build_template_record(template_id: str, source: dict[str, Any] | None = None) -> dict[str, Any]:
    source = source or {}
    meta = TEMPLATE_METADATA.get(template_id, {})
    record: dict[str, Any] = {
        "name": str(source.get("name") or meta.get("name") or template_id),
        "description": str(source.get("description") or meta.get("description") or ""),
        "ar": str(source.get("ar", "")),
        "en": str(source.get("en", "")),
        "fr": str(source.get("fr", "")),
    }
    if source.get("isCustom"):
        record["isCustom"] = True
    if source.get("createdAt"):
        record["createdAt"] = source["createdAt"]
    if source.get("updatedAt"):
        record["updatedAt"] = source["updatedAt"]
    return record


def _migrate_templates(templates: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """
    Canonicalize legacy template IDs and hide deprecated defaults.
    """
    changed = False
    migrated: dict[str, Any] = {}

    for template_id, template_data in (templates or {}).items():
        if not isinstance(template_data, dict):
            continue
        canonical_id = normalize_template_id(template_id)
        if canonical_id in DEPRECATED_TEMPLATE_IDS:
            changed = True
            continue

        existing = migrated.get(canonical_id, {})
        merged_source = dict(existing)
        merged_source.update(template_data)
        migrated[canonical_id] = _build_template_record(canonical_id, merged_source)

        if canonical_id != template_id:
            changed = True

    for template_id in _default_template_ids():
        if template_id not in migrated:
            migrated[template_id] = _build_template_record(template_id, {})
            changed = True

    return migrated, changed
