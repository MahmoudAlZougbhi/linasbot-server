"""Per-tenant AI usage limits for each end-user (chat customer).

Owners configure per-message and per-customer day/week/month caps in AI Setup.
Counters are keyed by (tenant_id, end_user_id, period). A new period key starts
at zero — that is the auto-reset when the window ends. Wallet unlimited does
not bypass these caps unless the owner sets ``unlimited`` on AI Limits.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from services.ai_limits_messages import customer_window_limit_message, reset_iso
from services.ai_usage_limits_settings import (
    CUSTOMER_CONTEXT_LIMIT_MESSAGE,
    CUSTOMER_IMAGE_LIMIT_MESSAGE,
    CUSTOMER_REPLY_LIMIT_MESSAGE,
    CUSTOMER_VOICE_LIMIT_MESSAGE,
    RECOMMENDED_CONTEXT_LINES_PER_DAY,
    RECOMMENDED_CONTEXT_LINES_PER_WEEK,
    RECOMMENDED_IMAGE_PER_DAY,
    RECOMMENDED_IMAGE_PER_MONTH,
    RECOMMENDED_IMAGE_PER_WEEK,
    AiLimitSettings,
    QuotaDecision,
    count_non_empty_lines,
    count_words,
    day_period_key,
    minutes_from_seconds,
    month_period_key,
    normalize_ai_limit_settings,
    recommended_defaults,
    truncate_text_to_words,
    week_period_key,
)
from storage.persistent_storage import SETTINGS_DIR, ensure_dirs

# Existing callers import these names from this module.
_ = (
    RECOMMENDED_CONTEXT_LINES_PER_DAY,
    RECOMMENDED_CONTEXT_LINES_PER_WEEK,
    RECOMMENDED_IMAGE_PER_DAY,
    RECOMMENDED_IMAGE_PER_MONTH,
    RECOMMENDED_IMAGE_PER_WEEK,
    count_non_empty_lines,
    count_words,
    minutes_from_seconds,
    truncate_text_to_words,
)

_COUNTER_KEYS = ("images", "context_lines", "replies", "voice_minutes")


class AiUsageLimitsService:
    """Persist per-tenant AI limit settings + per-end-user period counters."""

    def __init__(self, store_dir: Path | None = None) -> None:
        ensure_dirs()
        self._lock = threading.RLock()
        self._root = store_dir or (SETTINGS_DIR / "ai_limits")
        self._root.mkdir(parents=True, exist_ok=True)
        self._counters_dir = self._root / "counters"
        self._counters_dir.mkdir(parents=True, exist_ok=True)

    def _safe_tenant(self, tenant_id: str | None) -> str:
        tid = (tenant_id or "").strip().lower()
        if not tid:
            raise ValueError("tenant_id required")
        return tid.replace("/", "_").replace("..", "_")

    def _settings_path(self, tenant_id: str | None) -> Path:
        return self._root / f"{self._safe_tenant(tenant_id)}.json"

    def _counter_path(self, tenant_id: str | None, end_user_id: str, period_key: str) -> Path:
        safe_user = (end_user_id or "unknown").strip().replace("/", "_")[:180] or "unknown"
        safe_period = period_key.replace("/", "_")
        tenant_dir = self._counters_dir / self._safe_tenant(tenant_id)
        tenant_dir.mkdir(parents=True, exist_ok=True)
        return tenant_dir / f"{safe_user}__{safe_period}.json"

    def get_settings(self, tenant_id: str | None) -> AiLimitSettings:
        path = self._settings_path(tenant_id)
        with self._lock:
            if not path.exists():
                return normalize_ai_limit_settings(recommended_defaults())
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return normalize_ai_limit_settings(recommended_defaults())
            return normalize_ai_limit_settings(data if isinstance(data, dict) else None)

    def save_settings(self, tenant_id: str | None, updates: dict[str, Any]) -> AiLimitSettings:
        current = self.get_settings(tenant_id)
        merged = {**asdict(current), **(updates or {})}
        normalized = normalize_ai_limit_settings(merged)
        path = self._settings_path(tenant_id)
        with self._lock:
            path.write_text(json.dumps(asdict(normalized), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return normalized

    def _empty_counter(self) -> dict[str, int]:
        return {key: 0 for key in _COUNTER_KEYS}

    def _read_counter(self, path: Path) -> dict[str, int]:
        empty = self._empty_counter()
        if not path.exists():
            return empty
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return empty
            out = dict(empty)
            for key in _COUNTER_KEYS:
                out[key] = max(0, int(data.get(key) or 0))
            return out
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return empty

    def _write_counter(self, path: Path, data: dict[str, int]) -> None:
        payload = {key: int(data.get(key) or 0) for key in _COUNTER_KEYS}
        payload["updated_at"] = time.time()
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def get_usage(
        self,
        tenant_id: str | None,
        end_user_id: str,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        day_key = day_period_key(now)
        week_key = week_period_key(now)
        month_key = month_period_key(now)
        with self._lock:
            day = self._read_counter(self._counter_path(tenant_id, end_user_id, day_key))
            week = self._read_counter(self._counter_path(tenant_id, end_user_id, week_key))
            month = self._read_counter(self._counter_path(tenant_id, end_user_id, month_key))
        return {
            "day": {"period": day_key, **day},
            "week": {"period": week_key, **week},
            "month": {"period": month_key, **month},
        }

    def _check_metric(
        self,
        *,
        settings: AiLimitSettings,
        used_day: int,
        used_week: int,
        used_month: int,
        amount: int,
        day_limit: int,
        week_limit: int,
        month_limit: int,
        enforce_day: bool,
        enforce_week: bool,
        enforce_month: bool,
        customer_message: str,
        metric: str,
        kind: str,
        now: datetime | None = None,
        lang: str | None = None,
    ) -> QuotaDecision:
        if settings.unlimited:
            return QuotaDecision(allowed=True, allowed_amount=amount, reason="unlimited")
        amount = max(0, int(amount))
        if amount <= 0:
            return QuotaDecision(allowed=True, allowed_amount=0, reason="zero_amount")

        remaining = amount
        if enforce_day:
            remaining = min(remaining, max(0, day_limit - used_day))
        if enforce_week:
            remaining = min(remaining, max(0, week_limit - used_week))
        if enforce_month:
            remaining = min(remaining, max(0, month_limit - used_month))

        if remaining <= 0:
            period = "day"
            limit, used = day_limit, used_day
            if enforce_month and used_month >= month_limit:
                period, limit, used = "month", month_limit, used_month
            elif enforce_week and used_week >= week_limit:
                period, limit, used = "week", week_limit, used_week
            elif enforce_day and used_day >= day_limit:
                period, limit, used = "day", day_limit, used_day
            msg = customer_window_limit_message(kind=kind, period=period, lang=lang, now=now)
            return QuotaDecision(
                allowed=False,
                reason=f"{metric}_{period}_limit",
                remaining=0,
                limit=limit,
                used=used,
                period=period,
                customer_message=msg or customer_message,
                allowed_amount=0,
                reset_at=reset_iso(period, now),
            )

        binding_period = None
        binding_limit = None
        binding_used = None
        if enforce_day and remaining == max(0, day_limit - used_day):
            binding_period, binding_limit, binding_used = "day", day_limit, used_day
        elif enforce_week and remaining == max(0, week_limit - used_week):
            binding_period, binding_limit, binding_used = "week", week_limit, used_week
        elif enforce_month:
            binding_period, binding_limit, binding_used = "month", month_limit, used_month

        truncated = remaining < amount
        msg = None
        reset = None
        if truncated and binding_period:
            msg = customer_window_limit_message(kind=kind, period=binding_period, lang=lang, now=now)
            reset = reset_iso(binding_period, now)
        return QuotaDecision(
            allowed=True,
            reason="ok" if not truncated else f"{metric}_truncated",
            remaining=remaining,
            limit=binding_limit,
            used=binding_used,
            period=binding_period,
            allowed_amount=remaining,
            customer_message=msg,
            reset_at=reset,
            truncated=truncated,
        )

    def _consume_metric(
        self,
        tenant_id: str | None,
        end_user_id: str,
        *,
        metric_key: str,
        amount: int,
        now: datetime | None = None,
    ) -> None:
        consume = max(0, int(amount))
        if consume <= 0:
            return
        day_key = day_period_key(now)
        week_key = week_period_key(now)
        month_key = month_period_key(now)
        with self._lock:
            for period in (day_key, week_key, month_key):
                path = self._counter_path(tenant_id, end_user_id, period)
                data = self._read_counter(path)
                data[metric_key] = int(data[metric_key]) + consume
                self._write_counter(path, data)

    def check_image_quota(
        self,
        tenant_id: str | None,
        end_user_id: str,
        *,
        amount: int = 1,
        now: datetime | None = None,
        lang: str | None = None,
    ) -> QuotaDecision:
        settings = self.get_settings(tenant_id)
        usage = self.get_usage(tenant_id, end_user_id, now=now)
        requested = max(0, int(amount))
        want = max(0, min(requested, settings.photos_per_message))
        if requested > 0 and want <= 0 and not settings.unlimited:
            return QuotaDecision(
                allowed=False,
                reason="photos_per_message_limit",
                remaining=0,
                limit=settings.photos_per_message,
                used=0,
                period="message",
                customer_message=CUSTOMER_IMAGE_LIMIT_MESSAGE,
                allowed_amount=0,
            )
        return self._check_metric(
            settings=settings,
            used_day=int(usage["day"]["images"]),
            used_week=int(usage["week"]["images"]),
            used_month=int(usage["month"]["images"]),
            amount=want,
            day_limit=settings.image_per_day,
            week_limit=settings.image_per_week,
            month_limit=settings.image_per_month,
            enforce_day=settings.enforce_image_day,
            enforce_week=settings.enforce_image_week,
            enforce_month=settings.enforce_image_month,
            customer_message=CUSTOMER_IMAGE_LIMIT_MESSAGE,
            metric="image",
            kind="image",
            now=now,
            lang=lang,
        )

    def consume_images(
        self,
        tenant_id: str | None,
        end_user_id: str,
        *,
        amount: int = 1,
        now: datetime | None = None,
        lang: str | None = None,
    ) -> QuotaDecision:
        decision = self.check_image_quota(tenant_id, end_user_id, amount=amount, now=now, lang=lang)
        if not decision.allowed or decision.allowed_amount <= 0:
            return decision
        self._consume_metric(tenant_id, end_user_id, metric_key="images", amount=decision.allowed_amount, now=now)
        return decision

    def check_reply_quota(
        self,
        tenant_id: str | None,
        end_user_id: str,
        *,
        amount: int = 1,
        now: datetime | None = None,
        lang: str | None = None,
    ) -> QuotaDecision:
        settings = self.get_settings(tenant_id)
        usage = self.get_usage(tenant_id, end_user_id, now=now)
        return self._check_metric(
            settings=settings,
            used_day=int(usage["day"]["replies"]),
            used_week=int(usage["week"]["replies"]),
            used_month=int(usage["month"]["replies"]),
            amount=amount,
            day_limit=settings.text_replies_per_day,
            week_limit=settings.text_replies_per_week,
            month_limit=settings.text_replies_per_month,
            enforce_day=settings.enforce_replies_day,
            enforce_week=settings.enforce_replies_week,
            enforce_month=settings.enforce_replies_month,
            customer_message=CUSTOMER_REPLY_LIMIT_MESSAGE,
            metric="reply",
            kind="reply",
            now=now,
            lang=lang,
        )

    def consume_replies(
        self,
        tenant_id: str | None,
        end_user_id: str,
        *,
        amount: int = 1,
        now: datetime | None = None,
        lang: str | None = None,
    ) -> QuotaDecision:
        decision = self.check_reply_quota(tenant_id, end_user_id, amount=amount, now=now, lang=lang)
        if not decision.allowed or decision.allowed_amount <= 0:
            return decision
        self._consume_metric(tenant_id, end_user_id, metric_key="replies", amount=decision.allowed_amount, now=now)
        return decision

    def check_voice_quota(
        self,
        tenant_id: str | None,
        end_user_id: str,
        *,
        amount: int,
        now: datetime | None = None,
        lang: str | None = None,
    ) -> QuotaDecision:
        settings = self.get_settings(tenant_id)
        usage = self.get_usage(tenant_id, end_user_id, now=now)
        requested = max(0, int(amount))
        want = max(0, min(requested, settings.voice_minutes_per_message))
        if requested > 0 and want <= 0 and not settings.unlimited:
            return QuotaDecision(
                allowed=False,
                reason="voice_per_message_limit",
                remaining=0,
                limit=settings.voice_minutes_per_message,
                used=0,
                period="message",
                customer_message=CUSTOMER_VOICE_LIMIT_MESSAGE,
                allowed_amount=0,
            )
        return self._check_metric(
            settings=settings,
            used_day=int(usage["day"]["voice_minutes"]),
            used_week=int(usage["week"]["voice_minutes"]),
            used_month=int(usage["month"]["voice_minutes"]),
            amount=want,
            day_limit=settings.voice_minutes_per_day,
            week_limit=settings.voice_minutes_per_week,
            month_limit=settings.voice_minutes_per_month,
            enforce_day=settings.enforce_voice_day,
            enforce_week=settings.enforce_voice_week,
            enforce_month=settings.enforce_voice_month,
            customer_message=CUSTOMER_VOICE_LIMIT_MESSAGE,
            metric="voice",
            kind="voice",
            now=now,
            lang=lang,
        )

    def consume_voice_minutes(
        self,
        tenant_id: str | None,
        end_user_id: str,
        *,
        amount: int,
        now: datetime | None = None,
        lang: str | None = None,
    ) -> QuotaDecision:
        decision = self.check_voice_quota(tenant_id, end_user_id, amount=amount, now=now, lang=lang)
        if not decision.allowed or decision.allowed_amount <= 0:
            return decision
        self._consume_metric(
            tenant_id, end_user_id, metric_key="voice_minutes", amount=decision.allowed_amount, now=now
        )
        return decision

    def check_context_line_quota(
        self,
        tenant_id: str | None,
        end_user_id: str,
        *,
        amount: int,
        now: datetime | None = None,
        lang: str | None = None,
    ) -> QuotaDecision:
        settings = self.get_settings(tenant_id)
        usage = self.get_usage(tenant_id, end_user_id, now=now)
        return self._check_metric(
            settings=settings,
            used_day=int(usage["day"]["context_lines"]),
            used_week=int(usage["week"]["context_lines"]),
            used_month=0,
            amount=amount,
            day_limit=settings.context_lines_per_day,
            week_limit=settings.context_lines_per_week,
            month_limit=settings.context_lines_per_week,
            enforce_day=settings.enforce_context_day,
            enforce_week=settings.enforce_context_week,
            enforce_month=False,
            customer_message=CUSTOMER_CONTEXT_LIMIT_MESSAGE,
            metric="context_lines",
            kind="words",
            now=now,
            lang=lang,
        )

    def consume_context_lines(
        self,
        tenant_id: str | None,
        end_user_id: str,
        *,
        amount: int,
        now: datetime | None = None,
        lang: str | None = None,
    ) -> QuotaDecision:
        decision = self.check_context_line_quota(tenant_id, end_user_id, amount=amount, now=now, lang=lang)
        consume = int(decision.allowed_amount or 0)
        if consume <= 0:
            return decision
        self._consume_metric(tenant_id, end_user_id, metric_key="context_lines", amount=consume, now=now)
        return decision

    def truncate_text_to_line_budget(self, text: str, max_lines: int) -> str:
        if max_lines <= 0:
            return ""
        kept: list[str] = []
        count = 0
        for line in str(text).splitlines():
            if line.strip():
                if count >= max_lines:
                    break
                count += 1
            kept.append(line)
        return "\n".join(kept)


ai_usage_limits_service = AiUsageLimitsService()
