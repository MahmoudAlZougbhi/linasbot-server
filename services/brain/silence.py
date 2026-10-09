"""Customer outbound silence: log failures, never compose a fallback line."""

from __future__ import annotations

from typing import Any


def log_customer_generation_failure(
    *,
    stage: str,
    exc: BaseException | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Structured log for Brain/Terra failures. Returns metadata; never customer text."""
    payload = dict(extra or {})
    if exc is not None:
        payload.setdefault("exception_class", type(exc).__name__)
        payload.setdefault("blocker", f"{type(exc).__name__}: {str(exc)[:200]}")
    payload.setdefault("stage", stage)
    payload.setdefault("customer_silence", True)
    cls = str(payload.get("exception_class") or "None")
    blocker = str(payload.get("blocker") or "")[:200]
    print(f"customer_reply_v2 failed closed: {cls}: {blocker or stage}")
    from services.platform.feature_flags import flag_enabled

    if flag_enabled("dm_failure_status"):
        from services.live_chat.ai_failed import note_ai_failed

        note_ai_failed(conversation_id=str(payload.get("conversation_id") or ""), stage=stage)
    return payload
