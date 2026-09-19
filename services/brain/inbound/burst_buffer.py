"""Customer DM burst debounce: quiet window after last inbound, max-wait cap.

One Terra turn per flushed burst. While a conversation is flushing, inbound
chunks stay buffered — the sleeper is not cancelled and a second agentic run
must not start. Follow-up after the current turn drains leftovers.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import config

_log = logging.getLogger("uvicorn.error")
_FLUSHING: set[str] = set()


def is_flushing(user_id: str) -> bool:
    return str(user_id) in _FLUSHING


def begin_flush(user_id: str) -> bool:
    key = str(user_id)
    if key in _FLUSHING:
        return False
    _FLUSHING.add(key)
    return True


def end_flush(user_id: str) -> None:
    _FLUSHING.discard(str(user_id))


def reset_flushing_for_tests() -> None:
    _FLUSHING.clear()


def join_burst_texts(texts: list[str]) -> str:
    parts = [str(item).strip() for item in texts if str(item).strip()]
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    return "\n".join(f"- {part}" for part in parts)


def join_chunk_dicts(chunks: list[dict[str, Any]]) -> str:
    return join_burst_texts([str(item.get("text") or "") for item in chunks])


def sleep_seconds(*, quiet: float, started_at: float | None, now: float | None = None) -> float:
    from services.scale.message_combine_policy import combine_max_wait_seconds

    wait = max(0.0, float(quiet))
    if started_at is None:
        return wait
    elapsed = (time.time() if now is None else float(now)) - float(started_at)
    remaining_max = combine_max_wait_seconds() - elapsed
    return max(0.0, min(wait, remaining_max))


def log_flush(
    user_id: str,
    *,
    reason: str,
    chunk_count: int = 0,
    has_media: bool = False,
    extra: str = "",
) -> None:
    _log.info(
        "[dm-burst] flush reason=%s user=%s chunks=%d media=%s %s",
        reason,
        str(user_id)[:80],
        int(chunk_count),
        "1" if has_media else "0",
        extra,
    )


def peek_has_pending(user_id: str) -> bool:
    from services.scale.message_combine_store import combine_redis_available, peek_pending

    if combine_redis_available() and peek_pending(user_id):
        return True
    pending = config.user_pending_messages.get(user_id)
    return bool(pending)


def _has_media(user_data: dict[str, Any]) -> bool:
    if user_data.get("user_image_base64") or user_data.get("inbound_attachment_types"):
        return True
    media = user_data.get("inbound_media")
    return bool(isinstance(media, dict) and media)


def drain_burst_text(user_id: str, user_data: dict[str, Any]) -> tuple[str, str, int]:
    """Drain Redis/in-memory burst. Returns (text, reason, chunk_count)."""
    from services.scale.message_combine_store import (
        combine_redis_available,
        drain_if_due,
        generation_is_current,
    )

    combined = ""
    reason = "empty"
    chunk_count = 0
    if combine_redis_available():
        gen = int(user_data.get("_combine_generation") or 0)
        if gen and not generation_is_current(user_id, gen):
            return "", "superseded", 0
        redis_chunks = drain_if_due(user_id)
        forced = False
        if redis_chunks is None:
            redis_chunks = drain_if_due(user_id, force=True)
            forced = True
        if redis_chunks:
            combined = join_chunk_dicts(redis_chunks)
            chunk_count = len(redis_chunks)
            reason = "max_wait" if user_data.get("_burst_max_wait_hit") else ("force" if forced else "quiet")
            config.user_pending_messages[user_id].clear()
            extra_mids = [str(item.get("mid") or "") for item in redis_chunks if str(item.get("mid") or "")]
            extra_events = [str(item.get("event_id") or "") for item in redis_chunks if str(item.get("event_id") or "")]
            if extra_events:
                user_data["_combine_event_ids"] = extra_events
            if extra_mids:
                batch = list(user_data.get("_batch_inbound_mids") or [])
                for mid in extra_mids:
                    if mid not in batch:
                        batch.append(mid)
                user_data["_batch_inbound_mids"] = batch
    if not combined:
        combined, reason, chunk_count = _drain_memory(user_id, user_data)
    if _has_media(user_data) and combined:
        reason = "media" if reason in {"quiet", "empty", "single"} else f"{reason}+media"
    return combined, reason, chunk_count


def _drain_memory(user_id: str, user_data: dict[str, Any]) -> tuple[str, str, int]:
    if not config.user_pending_messages[user_id]:
        try:
            from services.scale.conversation_state_redis import get_pending_messages
            from services.scale.redis_claims import redis_claims_fail_closed

            remote_pending = get_pending_messages(user_id)
            if remote_pending:
                config.user_pending_messages[user_id].extend(remote_pending)
            elif redis_claims_fail_closed() and remote_pending is None:
                pass
        except Exception:
            pass
    if config.user_pending_messages[user_id]:
        texts = [str(item) for item in list(config.user_pending_messages[user_id])]
        combined = join_burst_texts(texts)
        chunk_count = len([item for item in texts if str(item).strip()])
        config.user_pending_messages[user_id].clear()
        try:
            from services.scale.conversation_state_redis import set_pending_messages

            set_pending_messages(user_id, [])
        except Exception:
            pass
        user_data.pop("_dashboard_last_message_for_fallback", None)
        user_data.pop("_dashboard_test_turn_sticky", None)
        reason = "quiet" if chunk_count > 1 else "single"
        return combined, reason, chunk_count
    if user_data.get("_dashboard_test_simulation"):
        fb = user_data.pop("_dashboard_last_message_for_fallback", None)
        if fb and str(fb).strip():
            return str(fb).strip(), "dashboard_fallback", 1
        sticky = user_data.pop("_dashboard_test_turn_sticky", None)
        if sticky and str(sticky).strip():
            return str(sticky).strip(), "dashboard_sticky", 1
    return "", "empty", 0
