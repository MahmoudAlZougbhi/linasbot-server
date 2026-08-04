"""Per-tenant AI capability limits for each end-user (chat customer).

Owners configure image-analysis and context-read quotas (per day / per week).
Counters are keyed by (tenant_id, end_user_id, period). Unlimited token-wallet
bypass does NOT bypass these abuse caps unless the owner explicitly enables
``unlimited`` on the AI Limits settings.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from storage.persistent_storage import SETTINGS_DIR, ensure_dirs

# Recommended defaults shown in Settings (owner can change).
RECOMMENDED_IMAGE_PER_DAY = 20
RECOMMENDED_IMAGE_PER_WEEK = 100
RECOMMENDED_CONTEXT_LINES_PER_DAY = 500
RECOMMENDED_CONTEXT_LINES_PER_WEEK = 2000

# Soft ceiling when "unlimited" is off but owner sets absurd values.
_HARD_MAX_IMAGES = 100_000
_HARD_MAX_LINES = 1_000_000

CUSTOMER_IMAGE_LIMIT_MESSAGE = (
    "Thanks for the photos. I've reached today's image review limit for this chat, "
    "so I can't analyze more images right now. Please send a text description of what "
    "you need, or try again later."
)

CUSTOMER_CONTEXT_LIMIT_MESSAGE = (
    "I can still help with a shorter question. Please send a brief message about what "
    "you need and I'll answer from what I can cover right now."
)


@dataclass(frozen=True)
class AiLimitSettings:
    unlimited: bool = False
    image_per_day: int = RECOMMENDED_IMAGE_PER_DAY
    image_per_week: int = RECOMMENDED_IMAGE_PER_WEEK
    context_lines_per_day: int = RECOMMENDED_CONTEXT_LINES_PER_DAY
    context_lines_per_week: int = RECOMMENDED_CONTEXT_LINES_PER_WEEK
    enforce_image_day: bool = True
    enforce_image_week: bool = True
    enforce_context_day: bool = True
    enforce_context_week: bool = True

    def to_public_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "recommended": recommended_defaults(),
            "definitions": {
                "image": (
                    "Counts each image the AI analyzes for one Messenger/Instagram/"
                    "WhatsApp end-user within the period."
                ),
                "context_line": (
                    "Counts non-empty lines of retrieved knowledge plus message/"
                    "conversation context assembled for the AI for one end-user."
                ),
            },
        }


def recommended_defaults() -> dict[str, Any]:
    return {
        "unlimited": False,
        "image_per_day": RECOMMENDED_IMAGE_PER_DAY,
        "image_per_week": RECOMMENDED_IMAGE_PER_WEEK,
        "context_lines_per_day": RECOMMENDED_CONTEXT_LINES_PER_DAY,
        "context_lines_per_week": RECOMMENDED_CONTEXT_LINES_PER_WEEK,
        "enforce_image_day": True,
        "enforce_image_week": True,
        "enforce_context_day": True,
        "enforce_context_week": True,
        "note": "Suggested starting values for a typical clinic. Not Meta-approved quotas.",
    }


def _clamp_int(value: Any, *, default: int, lo: int = 0, hi: int = _HARD_MAX_LINES) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


def normalize_ai_limit_settings(raw: dict[str, Any] | None) -> AiLimitSettings:
    data = raw if isinstance(raw, dict) else {}
    return AiLimitSettings(
        unlimited=bool(data.get("unlimited", False)),
        image_per_day=_clamp_int(
            data.get("image_per_day"), default=RECOMMENDED_IMAGE_PER_DAY, hi=_HARD_MAX_IMAGES
        ),
        image_per_week=_clamp_int(
            data.get("image_per_week"), default=RECOMMENDED_IMAGE_PER_WEEK, hi=_HARD_MAX_IMAGES
        ),
        context_lines_per_day=_clamp_int(
            data.get("context_lines_per_day"),
            default=RECOMMENDED_CONTEXT_LINES_PER_DAY,
            hi=_HARD_MAX_LINES,
        ),
        context_lines_per_week=_clamp_int(
            data.get("context_lines_per_week"),
            default=RECOMMENDED_CONTEXT_LINES_PER_WEEK,
            hi=_HARD_MAX_LINES,
        ),
        enforce_image_day=bool(data.get("enforce_image_day", True)),
        enforce_image_week=bool(data.get("enforce_image_week", True)),
        enforce_context_day=bool(data.get("enforce_context_day", True)),
        enforce_context_week=bool(data.get("enforce_context_week", True)),
    )


def count_non_empty_lines(text: str | None) -> int:
    if not text:
        return 0
    return sum(1 for line in str(text).splitlines() if line.strip())


def _utc_now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(UTC)
    if now.tzinfo is None:
        return now.replace(tzinfo=UTC)
    return now.astimezone(UTC)


def day_period_key(now: datetime | None = None) -> str:
    dt = _utc_now(now)
    return f"day:{dt.date().isoformat()}"


def week_period_key(now: datetime | None = None) -> str:
    dt = _utc_now(now)
    iso = dt.isocalendar()
    return f"week:{iso.year}-W{iso.week:02d}"


@dataclass
class QuotaDecision:
    allowed: bool
    reason: str | None = None
    remaining: int | None = None
    limit: int | None = None
    used: int | None = None
    period: str | None = None
    customer_message: str | None = None
    allowed_amount: int = 0

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "remaining": self.remaining,
            "limit": self.limit,
            "used": self.used,
            "period": self.period,
            "customer_message": self.customer_message,
            "allowed_amount": self.allowed_amount,
        }


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
        tid = (tenant_id or "linas").strip().lower() or "linas"
        return tid.replace("/", "_").replace("..", "_")

    def _settings_path(self, tenant_id: str) -> Path:
        return self._root / f"{self._safe_tenant(tenant_id)}.json"

    def _counter_path(self, tenant_id: str, end_user_id: str, period_key: str) -> Path:
        safe_user = (end_user_id or "unknown").strip().replace("/", "_")[:180] or "unknown"
        safe_period = period_key.replace("/", "_")
        tenant_dir = self._counters_dir / self._safe_tenant(tenant_id)
        tenant_dir.mkdir(parents=True, exist_ok=True)
        return tenant_dir / f"{safe_user}__{safe_period}.json"

    def get_settings(self, tenant_id: str | None) -> AiLimitSettings:
        path = self._settings_path(tenant_id or "linas")
        with self._lock:
            if not path.exists():
                # New SaaS tenants (and linas until configured) get recommended finite defaults.
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
        path = self._settings_path(tenant_id or "linas")
        with self._lock:
            path.write_text(json.dumps(asdict(normalized), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return normalized

    def _read_counter(self, path: Path) -> dict[str, int]:
        if not path.exists():
            return {"images": 0, "context_lines": 0}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return {"images": 0, "context_lines": 0}
            return {
                "images": max(0, int(data.get("images") or 0)),
                "context_lines": max(0, int(data.get("context_lines") or 0)),
            }
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return {"images": 0, "context_lines": 0}

    def _write_counter(self, path: Path, data: dict[str, int]) -> None:
        payload = {
            "images": int(data.get("images") or 0),
            "context_lines": int(data.get("context_lines") or 0),
            "updated_at": time.time(),
        }
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
        with self._lock:
            day = self._read_counter(self._counter_path(tenant_id or "linas", end_user_id, day_key))
            week = self._read_counter(self._counter_path(tenant_id or "linas", end_user_id, week_key))
        return {"day": {"period": day_key, **day}, "week": {"period": week_key, **week}}

    def _check_metric(
        self,
        *,
        settings: AiLimitSettings,
        used_day: int,
        used_week: int,
        amount: int,
        day_limit: int,
        week_limit: int,
        enforce_day: bool,
        enforce_week: bool,
        customer_message: str,
        metric: str,
    ) -> QuotaDecision:
        if settings.unlimited:
            return QuotaDecision(allowed=True, allowed_amount=amount, reason="unlimited")
        amount = max(0, int(amount))
        if amount <= 0:
            return QuotaDecision(allowed=True, allowed_amount=0, reason="zero_amount")

        remaining_day = day_limit - used_day if enforce_day else amount
        remaining_week = week_limit - used_week if enforce_week else amount
        remaining = amount
        if enforce_day:
            remaining = min(remaining, max(0, remaining_day))
        if enforce_week:
            remaining = min(remaining, max(0, remaining_week))

        if remaining <= 0:
            period = "day" if enforce_day and used_day >= day_limit else "week"
            limit = day_limit if period == "day" else week_limit
            used = used_day if period == "day" else used_week
            return QuotaDecision(
                allowed=False,
                reason=f"{metric}_{period}_limit",
                remaining=0,
                limit=limit,
                used=used,
                period=period,
                customer_message=customer_message,
                allowed_amount=0,
            )

        # Partial allowance (e.g. 3 lines left but 10 requested) — caller truncates.
        binding_period = None
        binding_limit = None
        binding_used = None
        if enforce_day and remaining == max(0, remaining_day):
            binding_period = "day"
            binding_limit = day_limit
            binding_used = used_day
        elif enforce_week:
            binding_period = "week"
            binding_limit = week_limit
            binding_used = used_week

        return QuotaDecision(
            allowed=True,
            reason="ok" if remaining >= amount else f"{metric}_truncated",
            remaining=remaining,
            limit=binding_limit,
            used=binding_used,
            period=binding_period,
            allowed_amount=remaining if remaining < amount else amount,
            customer_message=None if remaining >= amount else customer_message,
        )

    def check_image_quota(
        self,
        tenant_id: str | None,
        end_user_id: str,
        *,
        amount: int = 1,
        now: datetime | None = None,
    ) -> QuotaDecision:
        settings = self.get_settings(tenant_id)
        usage = self.get_usage(tenant_id, end_user_id, now=now)
        return self._check_metric(
            settings=settings,
            used_day=int(usage["day"]["images"]),
            used_week=int(usage["week"]["images"]),
            amount=amount,
            day_limit=settings.image_per_day,
            week_limit=settings.image_per_week,
            enforce_day=settings.enforce_image_day,
            enforce_week=settings.enforce_image_week,
            customer_message=CUSTOMER_IMAGE_LIMIT_MESSAGE,
            metric="image",
        )

    def consume_images(
        self,
        tenant_id: str | None,
        end_user_id: str,
        *,
        amount: int = 1,
        now: datetime | None = None,
    ) -> QuotaDecision:
        decision = self.check_image_quota(tenant_id, end_user_id, amount=amount, now=now)
        if not decision.allowed or decision.allowed_amount <= 0:
            return decision
        day_key = day_period_key(now)
        week_key = week_period_key(now)
        with self._lock:
            for period in (day_key, week_key):
                path = self._counter_path(tenant_id or "linas", end_user_id, period)
                data = self._read_counter(path)
                data["images"] = int(data["images"]) + int(decision.allowed_amount)
                self._write_counter(path, data)
        return decision

    def check_context_line_quota(
        self,
        tenant_id: str | None,
        end_user_id: str,
        *,
        amount: int,
        now: datetime | None = None,
    ) -> QuotaDecision:
        settings = self.get_settings(tenant_id)
        usage = self.get_usage(tenant_id, end_user_id, now=now)
        return self._check_metric(
            settings=settings,
            used_day=int(usage["day"]["context_lines"]),
            used_week=int(usage["week"]["context_lines"]),
            amount=amount,
            day_limit=settings.context_lines_per_day,
            week_limit=settings.context_lines_per_week,
            enforce_day=settings.enforce_context_day,
            enforce_week=settings.enforce_context_week,
            customer_message=CUSTOMER_CONTEXT_LIMIT_MESSAGE,
            metric="context_lines",
        )

    def consume_context_lines(
        self,
        tenant_id: str | None,
        end_user_id: str,
        *,
        amount: int,
        now: datetime | None = None,
    ) -> QuotaDecision:
        decision = self.check_context_line_quota(tenant_id, end_user_id, amount=amount, now=now)
        consume = int(decision.allowed_amount or 0)
        if consume <= 0:
            return decision
        day_key = day_period_key(now)
        week_key = week_period_key(now)
        with self._lock:
            for period in (day_key, week_key):
                path = self._counter_path(tenant_id or "linas", end_user_id, period)
                data = self._read_counter(path)
                data["context_lines"] = int(data["context_lines"]) + consume
                self._write_counter(path, data)
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
