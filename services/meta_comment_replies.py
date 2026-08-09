"""Process Meta public comment events and post one AI reply per comment."""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass
from typing import Any

import httpx

from services.meta_app_registry import APP_A_KEY, MetaAssetBinding
from services.meta_comment_events import ResolvedMetaCommentEvent
from services.meta_comment_reply_settings import get_comment_reply_setting

_runtime_logger = logging.getLogger("uvicorn.error")

_COMMENT_RATE_WINDOW_SECONDS = 60.0
_COMMENT_RATE_LIMIT_PER_ASSET = 30
_RATE_BUCKETS: dict[str, deque[float]] = {}
_SENT_REPLY_IDS: dict[str, float] = {}
_SENT_REPLY_TTL_SECONDS = 86400.0

_COMMENT_SYSTEM_RULES = (
    "You are replying publicly to a social media comment for a business. "
    "Keep the reply short (1-3 sentences), friendly, and suitable for a public thread. "
    "Do not provide medical diagnosis or guaranteed results. "
    "Do not invent prices, discounts, appointments, or promotions. "
    "Do not reveal private customer data. "
    "Do not ask for personal information in public. "
    "If booking or personal details are needed, briefly invite the person to send a private message. "
    "If you are not confident from approved business content, give a brief honest response and invite private contact."
)


@dataclass(frozen=True)
class CommentReplyResult:
    status: str
    reason: str = ""
    reply_id: str = ""


def _rate_limit_key(binding: MetaAssetBinding) -> str:
    return f"{binding.tenant_id}:{binding.app_key}:{binding.channel}:{binding.asset_id}"


def _rate_limit_allow(key: str) -> bool:
    now = time.time()
    bucket = _RATE_BUCKETS.setdefault(key, deque())
    while bucket and now - bucket[0] > _COMMENT_RATE_WINDOW_SECONDS:
        bucket.popleft()
    if len(bucket) >= _COMMENT_RATE_LIMIT_PER_ASSET:
        return False
    bucket.append(now)
    return True


def _sent_reply_cache_key(binding: MetaAssetBinding, comment_id: str) -> str:
    return f"{binding.binding_id}:{comment_id}"


def _mark_sent_reply(binding: MetaAssetBinding, comment_id: str) -> None:
    key = _sent_reply_cache_key(binding, comment_id)
    _SENT_REPLY_IDS[key] = time.time()
    cutoff = time.time() - _SENT_REPLY_TTL_SECONDS
    stale = [item for item, ts in _SENT_REPLY_IDS.items() if ts < cutoff]
    for item in stale:
        _SENT_REPLY_IDS.pop(item, None)


def _already_sent_reply(binding: MetaAssetBinding, comment_id: str) -> bool:
    key = _sent_reply_cache_key(binding, comment_id)
    ts = _SENT_REPLY_IDS.get(key)
    if not ts:
        return False
    if time.time() - ts > _SENT_REPLY_TTL_SECONDS:
        _SENT_REPLY_IDS.pop(key, None)
        return False
    return True


def _is_self_comment(event: dict[str, Any], binding: MetaAssetBinding) -> bool:
    author_id = str(event.get("author_id") or "").strip()
    if not author_id:
        return True
    if binding.channel == "facebook":
        return author_id == binding.page_id
    return author_id == binding.instagram_account_id or author_id == binding.asset_id


async def _graph_get_json(
    client: httpx.AsyncClient,
    path: str,
    *,
    token: str,
    params: dict[str, str] | None = None,
) -> dict[str, Any]:
    response = await client.get(path, params=params or {}, headers={"Authorization": f"Bearer {token}"})
    if response.status_code < 200 or response.status_code >= 300:
        return {}
    try:
        payload = response.json()
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {}


async def _graph_post_form(
    client: httpx.AsyncClient,
    path: str,
    *,
    token: str,
    data: dict[str, str],
) -> tuple[bool, str, dict[str, Any]]:
    response = await client.post(path, data=data, headers={"Authorization": f"Bearer {token}"})
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    if response.status_code < 200 or response.status_code >= 300:
        return False, f"http_{response.status_code}", payload if isinstance(payload, dict) else {}
    if not isinstance(payload, dict):
        return False, "invalid_response", {}
    if payload.get("error"):
        return False, "graph_error", payload
    reply_id = str(payload.get("id") or "").strip()
    return True, "ok", payload if reply_id else {"id": reply_id}


async def _comment_has_page_reply(
    client: httpx.AsyncClient,
    *,
    comment_id: str,
    page_id: str,
    token: str,
    graph_version: str,
) -> bool:
    payload = await _graph_get_json(
        client,
        f"https://graph.facebook.com/{graph_version}/{comment_id}/comments",
        token=token,
        params={"fields": "from{id}", "limit": "10"},
    )
    rows = payload.get("data")
    if not isinstance(rows, list):
        return False
    for row in rows:
        if not isinstance(row, dict):
            continue
        from_raw = row.get("from")
        from_dict = from_raw if isinstance(from_raw, dict) else {}
        if str(from_dict.get("id") or "") == page_id:
            return True
    return False


async def _generate_comment_reply_text(
    *,
    tenant_id: str,
    comment_text: str,
    instructions: str,
    channel: str,
) -> str | None:
    owner_hint = f"\nOwner instructions: {instructions.strip()}" if instructions else ""
    comment_context = (
        f"{_COMMENT_SYSTEM_RULES}{owner_hint}\n"
        f"Channel: {channel} public comment.\n"
        f"Customer comment: {comment_text.strip()}\n"
    )

    from services.cm.constants import tenant_uses_cm_runtime

    if tenant_uses_cm_runtime(tenant_id):
        from services.cm.answer_generation import (
            UsageAccumulator,
            generate_answer_with_usage,
            make_regenerate_fn_with_usage,
        )
        from services.cm.runtime_pipeline import finalize_response, prepare_response

        outcome = await prepare_response(
            tenant_id=tenant_id,
            message=comment_text,
            detected_language="ar",
            response_language="ar",
        )
        if outcome.stop:
            reply = (outcome.reply or "").strip()
            return reply[:900] if reply else None
        packet = outcome.packet
        if packet is None:
            return None
        usage_acc = UsageAccumulator()
        try:
            gen_result = await generate_answer_with_usage(f"{comment_context}\n{comment_text}", packet)
            candidate_text = gen_result.text
            if gen_result.prompt_tokens is not None or gen_result.completion_tokens is not None:
                usage_acc.prompt_tokens += int(gen_result.prompt_tokens or 0)
                usage_acc.completion_tokens += int(gen_result.completion_tokens or 0)
                usage_acc.calls += max(int(gen_result.call_count or 1), 1)
                usage_acc.models.append(gen_result.model)
        except Exception:
            return None
        restricted_ids = set(outcome.metadata.get("restricted_topic_active_ids") or [])
        result = await finalize_response(
            candidate_text=candidate_text,
            packet=packet,
            restricted_topic_active_ids=restricted_ids,
            regenerate_fn=make_regenerate_fn_with_usage(comment_text, packet, usage_acc),
        )
        text = str(result.text or "").strip()
        return text[:900] if text and result.ok else None

    from services.local_qa_service import local_qa_service

    tiered_match = await local_qa_service.find_match_with_tier(comment_text, "ar")
    if tiered_match and tiered_match.get("answer"):
        return str(tiered_match["answer"]).strip()[:900]
    return None


async def process_meta_comment_event(
    resolved: ResolvedMetaCommentEvent,
    *,
    simulation: bool = False,
    capture_send: list[dict[str, Any]] | None = None,
) -> CommentReplyResult:
    event = resolved.event
    binding = resolved.binding
    settings = resolved.settings
    comment_id = str(event.get("comment_id") or "").strip()

    if binding.app_key != APP_A_KEY:
        return CommentReplyResult(status="ignored", reason="app_b_not_supported")
    if binding.status != "active":
        return CommentReplyResult(status="ignored", reason="binding_not_active")
    if not comment_id:
        return CommentReplyResult(status="ignored", reason="missing_comment_id")
    if _is_self_comment(event, binding):
        return CommentReplyResult(status="ignored", reason="self_comment")
    if _already_sent_reply(binding, comment_id):
        return CommentReplyResult(status="ignored", reason="already_replied")

    reply_setting = get_comment_reply_setting(
        tenant_id=binding.tenant_id,
        app_key=binding.app_key,
        channel=binding.channel,
        asset_id=binding.asset_id,
    )

    from services.cm.actions import comments_enforcement_decision

    # Scope readiness is reported via Meta connections API / evaluate_comments_meta_readiness.
    # Webhook enforcement gates on published CM actions + per-asset switch (scopes enforced at enable-time).
    decision = comments_enforcement_decision(
        tenant_id=binding.tenant_id,
        channel=binding.channel,
        per_asset_enabled=bool(reply_setting.enabled),
        granted_scopes=None,
    )
    if not decision["allow"]:
        return CommentReplyResult(status="ignored", reason=str(decision["reason"]))

    rate_key = _rate_limit_key(binding)
    if not _rate_limit_allow(rate_key):
        return CommentReplyResult(status="ignored", reason="rate_limited")

    comment_text = str(event.get("text") or "").strip()
    if not comment_text:
        return CommentReplyResult(status="ignored", reason="empty_comment")

    graph_version = settings.graph_api_version or "v24.0"
    token = settings.page_access_token
    async with httpx.AsyncClient(timeout=20.0) as client:
        if await _comment_has_page_reply(
            client,
            comment_id=comment_id,
            page_id=binding.page_id,
            token=token,
            graph_version=graph_version,
        ):
            return CommentReplyResult(status="ignored", reason="human_replied")

        reply_text = await _generate_comment_reply_text(
            tenant_id=binding.tenant_id,
            comment_text=comment_text,
            instructions=reply_setting.instructions,
            channel=binding.channel,
        )
        if not reply_text:
            return CommentReplyResult(status="skipped", reason="no_confident_reply")

        if simulation:
            payload = {
                "comment_id": comment_id,
                "channel": binding.channel,
                "message": reply_text,
            }
            if capture_send is not None:
                capture_send.append(payload)
            _mark_sent_reply(binding, comment_id)
            return CommentReplyResult(status="simulated", reply_id="simulated")

        if binding.channel == "facebook":
            ok, reason, response = await _graph_post_form(
                client,
                f"https://graph.facebook.com/{graph_version}/{comment_id}/comments",
                token=token,
                data={"message": reply_text},
            )
        else:
            ok, reason, response = await _graph_post_form(
                client,
                f"https://graph.facebook.com/{graph_version}/{comment_id}/replies",
                token=token,
                data={"message": reply_text},
            )
        if not ok:
            _runtime_logger.error(
                "[meta-comment] reply_failed channel=%s reason=%s",
                binding.channel,
                reason,
            )
            return CommentReplyResult(status="failed", reason=reason)

        reply_id = str(response.get("id") or "").strip()
        _mark_sent_reply(binding, comment_id)
        _runtime_logger.info(
            "[meta-comment] reply_sent channel=%s tenant=%s asset=%s comment=%s",
            binding.channel,
            binding.tenant_id,
            binding.asset_id[-6:],
            comment_id[-8:],
        )
        return CommentReplyResult(status="sent", reply_id=reply_id)
