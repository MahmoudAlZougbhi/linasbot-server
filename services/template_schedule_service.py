"""
Template schedule persistence and validation.
"""

from __future__ import annotations

import json
import os
import re
import threading
from typing import Any, cast
from zoneinfo import ZoneInfo

from services.smart_messaging_catalog import (
    DAILY_TEMPLATE_IDS,
    get_default_schedule,
    normalize_template_id,
)

_TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


class TemplateScheduleService:
    """Manage per-template daily schedule settings under app_settings.smartMessaging."""

    def __init__(self) -> None:
        from storage.persistent_storage import APP_SETTINGS_FILE, ensure_dirs

        ensure_dirs()
        self.settings_file = APP_SETTINGS_FILE
        self._lock = threading.Lock()

    def _load_settings(self) -> dict[str, Any]:
        if not self.settings_file.exists():
            return {}

        try:
            with open(self.settings_file, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
            return {}
        except Exception:
            return {}

    def _save_settings(self, settings: dict[str, Any]) -> bool:
        try:
            os.makedirs(self.settings_file.parent, exist_ok=True)
            with open(self.settings_file, "w", encoding="utf-8") as f:
                json.dump(settings, f, ensure_ascii=False, indent=2)
            return True
        except Exception:
            return False

    def _ensure_schedules(self, settings: dict[str, Any]) -> dict[str, Any]:
        smart = settings.setdefault("smartMessaging", {})
        schedules = smart.setdefault("templateSchedules", {})
        # Legacy key attended_yesterday -> session_feedback (Meta template name)
        legacy_ay = schedules.pop("attended_yesterday", None)
        if isinstance(legacy_ay, dict) and "session_feedback" not in schedules:
            schedules["session_feedback"] = dict(legacy_ay)
        legacy_17 = schedules.pop("twenty_day_followup", None)
        if isinstance(legacy_17, dict) and "sent_17_days_after_last_session_new" not in schedules:
            schedules["sent_17_days_after_last_session_new"] = dict(legacy_17)
        legacy_om = schedules.pop("one_month_followup", None)
        if isinstance(legacy_om, dict) and "sent_17_days_after_last_session_new" not in schedules:
            schedules["sent_17_days_after_last_session_new"] = dict(legacy_om)
        legacy_ty = schedules.pop("post_session_feedback", None)
        if isinstance(legacy_ty, dict) and "thank_you_message_sent_after_session" not in schedules:
            schedules["thank_you_message_sent_after_session"] = dict(legacy_ty)

        for template_id in DAILY_TEMPLATE_IDS:
            existing = schedules.get(template_id)
            if not isinstance(existing, dict):
                schedules[template_id] = get_default_schedule(template_id)
                continue

            default_cfg = get_default_schedule(template_id)
            for key, value in default_cfg.items():
                if key not in existing:
                    existing[key] = value

        return cast(dict[str, Any], schedules)

    def _validate_timezone(self, tz_name: str) -> bool:
        if not tz_name:
            return False
        if ZoneInfo is None:
            # If zoneinfo is unavailable, accept value and rely on runtime fallback.
            return True
        try:
            ZoneInfo(tz_name)
            return True
        except Exception:
            return False

    def _sanitize_schedule_payload(self, payload: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
        sanitized = dict(current)

        if "enabled" in payload:
            sanitized["enabled"] = bool(payload.get("enabled"))

        if "sendTime" in payload:
            value = str(payload.get("sendTime", "")).strip()
            if not _TIME_RE.match(value):
                raise ValueError("sendTime must be in HH:MM format")
            sanitized["sendTime"] = value

        if "timezone" in payload:
            tz_name = str(payload.get("timezone", "")).strip()
            if not self._validate_timezone(tz_name):
                raise ValueError(f"Invalid timezone: {tz_name}")
            sanitized["timezone"] = tz_name

        if "delayHours" in payload:
            try:
                h = float(payload.get("delayHours") or 0)
            except (TypeError, ValueError) as e:
                raise ValueError("delayHours must be a number") from e
            sanitized["delayHours"] = max(0.5, min(72.0, h))

        return sanitized

    def get_all_schedules(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            settings = self._load_settings()
            schedules = self._ensure_schedules(settings)
            # Persist defaults lazily if missing
            self._save_settings(settings)
            return {k: dict(v) for k, v in schedules.items()}

    def get_schedule(self, template_id: str) -> dict[str, Any]:
        template_id = normalize_template_id(template_id)
        if template_id not in DAILY_TEMPLATE_IDS:
            raise ValueError(f"Template '{template_id}' does not support daily scheduling")
        schedules = self.get_all_schedules()
        return schedules.get(template_id, get_default_schedule(template_id))

    def update_schedule(self, template_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        template_id = normalize_template_id(template_id)
        if template_id not in DAILY_TEMPLATE_IDS:
            raise ValueError(f"Template '{template_id}' does not support daily scheduling")

        with self._lock:
            settings = self._load_settings()
            schedules = self._ensure_schedules(settings)
            current = schedules.get(template_id, get_default_schedule(template_id))
            updated = self._sanitize_schedule_payload(payload, current)
            schedules[template_id] = updated

            if not self._save_settings(settings):
                raise RuntimeError("Failed to save template schedules")

            return dict(updated)

    def get_enabled_daily_templates(self) -> dict[str, dict[str, Any]]:
        schedules = self.get_all_schedules()
        enabled = {}
        for template_id, cfg in schedules.items():
            if cfg.get("enabled", True):
                enabled[template_id] = cfg
        return enabled


template_schedule_service = TemplateScheduleService()
