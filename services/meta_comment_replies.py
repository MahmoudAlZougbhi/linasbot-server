"""Process Meta public comment events and post one AI reply per comment."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx

from services.meta_app_registry import APP_A_KEY, MetaAssetBinding
from services.meta_comment_events import ResolvedMetaCommentEvent
from services.meta_comment_reply_generate import generate_comment_reply_text as _generate_comment_reply_text
from services.meta_comment_reply_inspect import (
    MetaCommentReplyInspectionError,
    _comment_has_page_reply,
)
from services.meta_comment_reply_settings import get_comment_reply_setting
from services.meta_graph_routing import graph_api_url
from services.omnichannel.comment_limit import comment_send_allowed

_runtime_logger = logging.getLogger("uvicorn.error")

_RATE_BUCKETS: dict[str, list[float]] = {}
_SENT_REPLY_IDS: dict[str, float] = {}
_SENT_REPLY_TTL_SECONDS = 86400.0


@dataclass(frozen=True)
class CommentReplyResult:
    status: str
    reason: str = ""
    reply_id: str = ""


def _settle_generated_comment(
    *,
    binding: MetaAssetBinding,
    comment_id: str,
    inbound_event_id: str | None,
    accepted: bool,
    reply_id: str = "",
) -> None:
    from services.meta_comment_brain_send import _settle_comment_send

    _settle_comment_send(
        binding=binding,
        comment_id=comment_id,
        inbound_event_id=inbound_event_id,
        reply_id=reply_id,
        accepted=accepted,
    )


def _provider_rejection_is_definitive(reason: str) -> bool:
    """Only an explicit client rejection proves Meta did not accept the send."""

    safe_reason = str(reason or "").strip().lower()
    if safe_reason in {"empty_private_reply", "missing_comment_id", "missing_instagram_account"}:
        return True
    for prefix in ("http_", "graph_http_"):
        if not safe_reason.startswith(prefix):
            continue
        status_text = safe_reason[len(prefix) :].split("_", 1)[0]
        if status_text.isdigit():
            status = int(status_text)
            if 400 <= status < 500 and status not in {408, 425, 429}:
                return True
    return False


def comment_reply_requires_retry(result: CommentReplyResult) -> bool:
    """Return whether the durable event/claim must remain non-terminal."""

    return result.status == "failed" or result.reason == "rate_limited"


def _rate_limit_key(binding: MetaAssetBinding) -> str:
    return f"{binding.tenant_id}:{binding.app_key}:{binding.channel}:{binding.asset_id}"


def _rate_limit_allow(key: str) -> bool:
    tenant_id, app_key, channel, asset_id = (key.split(":", 3) + ["", "", "", ""])[:4]
    return comment_send_allowed(tenant_id=tenant_id, app_key=app_key, channel=channel, asset_id=asset_id)


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
    if author_id == binding.instagram_account_id or author_id == binding.asset_id:
        return True
    author_username = str(event.get("author_username") or "").strip().casefold()
    binding_username = str(binding.instagram_username or "").strip().casefold()
    return bool(author_username and binding_username and author_username == binding_username)


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
    if not reply_id:
        return False, "missing_reply_id", payload
    return True, "ok", payload


async def process_meta_comment_event(
    resolved: ResolvedMetaCommentEvent,
    *,
    simulation: bool = False,
    capture_send: list[dict[str, Any]] | None = None,
    inbound_event_id: str | None = None,
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

    from services.membership.comment_gate import CommentAutomationDenied, assert_comment_automation_allowed

    try:
        assert_comment_automation_allowed(binding.tenant_id)
    except CommentAutomationDenied:
        return CommentReplyResult(status="ignored", reason="comment_automation_plan_denied")

    reply_setting = get_comment_reply_setting(
        tenant_id=binding.tenant_id,
        app_key=binding.app_key,
        channel=binding.channel,
        asset_id=binding.asset_id,
    )

    from services.cm.actions import comments_enforcement_decision
    from services.meta_app_registry import get_meta_app_registry

    try:
        credential = get_meta_app_registry().get_credential(binding)
    except Exception:
        return CommentReplyResult(status="ignored", reason="credential_unavailable")

    decision = comments_enforcement_decision(
        tenant_id=binding.tenant_id,
        channel=binding.channel,
        per_asset_enabled=bool(reply_setting.enabled),
        binding=binding,
        credential=credential,
    )
    if not decision["allow"]:
        return CommentReplyResult(status="ignored", reason=str(decision["reason"]))

    rate_key = _rate_limit_key(binding)
    if not _rate_limit_allow(rate_key):
        return CommentReplyResult(status="ignored", reason="rate_limited")

    comment_text = str(event.get("text") or "").strip()
    if not comment_text:
        return CommentReplyResult(status="ignored", reason="empty_comment")

    from services.meta_comment_post_context import enrich_comment_event_post

    event = await enrich_comment_event_post(
        dict(event),
        binding=binding,
        token=str(settings.page_access_token or ""),
        graph_api_version=str(settings.graph_api_version or "v24.0"),
        allow_graph=not simulation,
    )
    post_id = str(event.get("post_id") or event.get("media_id") or "").strip()
    from services.cm.comment_rules import evaluate_published_comment_rules
    from services.cm.constants import tenant_uses_cm_runtime

    rule_decision = None
    if tenant_uses_cm_runtime(binding.tenant_id):
        rule_decision = evaluate_published_comment_rules(
            binding.tenant_id,
            comment_text=comment_text,
            channel=binding.channel,
            post_id=post_id,
            account_id=binding.asset_id,
        )
        if rule_decision.action == "ignore" and rule_decision.rule_mode != "ai_guidance":
            _mark_sent_reply(binding, comment_id)
            return CommentReplyResult(status="ignored", reason=rule_decision.reason or "comment_rule_ignore")

    graph_version = settings.graph_api_version or "v24.0"
    token = settings.page_access_token
    owner_id = binding.page_id if binding.channel == "facebook" else (binding.instagram_account_id or binding.asset_id)
    reply_list_path = f"{comment_id}/comments" if binding.channel == "facebook" else f"{comment_id}/replies"
    async with httpx.AsyncClient(timeout=20.0) as client:
        already_replied = False
        if not simulation:
            try:
                already_replied = await _comment_has_page_reply(
                    client,
                    comment_id=comment_id,
                    owner_id=owner_id,
                    token=token,
                    graph_url=graph_api_url(binding, graph_api_version=graph_version, path=reply_list_path),
                )
            except MetaCommentReplyInspectionError as exc:
                _runtime_logger.warning(
                    "[meta-comment] reply_dedupe_check_failed channel=%s reason=%s",
                    binding.channel,
                    str(exc),
                )
                return CommentReplyResult(status="failed", reason="reply_dedupe_check_failed")
        from services.meta_comment_rule_both import is_deterministic_comment_and_dm, maybe_handle_comment_and_dm
        from services.meta_comment_rule_dm import maybe_handle_static_dm
        from services.meta_comment_rule_modes import (
            allows_private_after_public_reply,
            is_static_comment_dm,
            is_static_public_comment,
        )

        reply_text: str | None = None
        if rule_decision is not None:
            if already_replied and not allows_private_after_public_reply(rule_decision):
                return CommentReplyResult(status="ignored", reason="human_replied")
            if is_deterministic_comment_and_dm(rule_decision):
                return await maybe_handle_comment_and_dm(
                    rule_decision=rule_decision,
                    binding=binding,
                    comment_id=comment_id,
                    simulation=simulation,
                    capture_send=capture_send,
                    inbound_event_id=inbound_event_id,
                    token=token,
                    graph_api_version=graph_version,
                    client=client,
                    skip_public=already_replied,
                )
            if is_static_comment_dm(rule_decision):
                return await maybe_handle_static_dm(
                    rule_decision=rule_decision,
                    binding=binding,
                    comment_id=comment_id,
                    simulation=simulation,
                    capture_send=capture_send,
                    inbound_event_id=inbound_event_id,
                    token=token,
                    graph_api_version=graph_version,
                    client=client,
                )
            if is_static_public_comment(rule_decision):
                reply_text = rule_decision.reply_text.strip()[:900]

        if reply_text is None:
            generated = await _generate_comment_reply_text(
                tenant_id=binding.tenant_id,
                comment_text=comment_text,
                instructions=reply_setting.instructions,
                channel=binding.channel,
                policy_text=(rule_decision.policy_text if rule_decision else ""),
                comment_context={
                    "conversation_id": f"comment:{binding.tenant_id}:{binding.channel}:{post_id or comment_id}",
                    "comment_id": comment_id,
                    "post_id": post_id,
                    "parent_id": str(event.get("parent_id") or ""),
                    "caption": str(event.get("caption") or event.get("post_caption") or ""),
                    "parent_comment": str(event.get("parent_comment") or event.get("parent_text") or ""),
                },
                asset_id=binding.asset_id,
                provider_sender_id=str(event.get("author_id") or "").strip(),
                provider_display_name=str(event.get("author_name") or "").strip(),
            )
            from services.customer_ai.comments.destinations import coerce_comment_destinations
            from services.meta_comment_brain_send import send_comment_destinations

            plan = coerce_comment_destinations(generated)
            if plan is None or not plan.has_any:
                _settle_generated_comment(
                    binding=binding,
                    comment_id=comment_id,
                    inbound_event_id=inbound_event_id,
                    accepted=False,
                )
                return CommentReplyResult(status="skipped", reason="no_confident_reply")
            if plan.private_text:
                return await send_comment_destinations(
                    plan=plan,
                    binding=binding,
                    comment_id=comment_id,
                    simulation=simulation,
                    capture_send=capture_send,
                    inbound_event_id=inbound_event_id,
                    token=token,
                    graph_api_version=graph_version,
                    client=client,
                    skip_public=already_replied,
                )
            reply_text = plan.public_text
        if not str(reply_text or "").strip():
            _settle_generated_comment(
                binding=binding,
                comment_id=comment_id,
                inbound_event_id=inbound_event_id,
                accepted=False,
            )
            return CommentReplyResult(status="skipped", reason="no_confident_reply")

        if simulation:
            payload = {
                "comment_id": comment_id,
                "channel": binding.channel,
                "message": reply_text,
                "delivery": "public_reply",
                "rule_id": (rule_decision.rule_id if rule_decision else ""),
            }
            if capture_send is not None:
                capture_send.append(payload)
            _mark_sent_reply(binding, comment_id)
            _settle_generated_comment(
                binding=binding,
                comment_id=comment_id,
                inbound_event_id=inbound_event_id,
                accepted=False,
                reply_id="simulated",
            )
            return CommentReplyResult(status="simulated", reply_id="simulated")

        from services.meta_controlled_evidence import meta_evidence_surface
        from services.meta_outbound_attempts import (
            MetaOutboundAttemptDecision,
            begin_meta_outbound_attempt,
            finish_meta_outbound_attempt,
        )

        public_attempt: MetaOutboundAttemptDecision | None = None
        if inbound_event_id:
            public_attempt = await begin_meta_outbound_attempt(
                event_id=inbound_event_id,
                surface=meta_evidence_surface(kind="meta_comment", channel=binding.channel),
                binding_id=binding.binding_id,
            )
            if public_attempt.kind == "duplicate_suppressed":
                _settle_generated_comment(
                    binding=binding,
                    comment_id=comment_id,
                    inbound_event_id=inbound_event_id,
                    accepted=False,
                )
                return CommentReplyResult(status="ignored", reason="already_replied")
            if public_attempt.kind == "needs_owner_action":
                return CommentReplyResult(status="skipped", reason="ambiguous_needs_owner_action")
        try:
            if binding.channel == "facebook":
                ok, reason, response = await _graph_post_form(
                    client,
                    graph_api_url(binding, graph_api_version=graph_version, path=f"{comment_id}/comments"),
                    token=token,
                    data={"message": reply_text},
                )
            else:
                ok, reason, response = await _graph_post_form(
                    client,
                    graph_api_url(binding, graph_api_version=graph_version, path=f"{comment_id}/replies"),
                    token=token,
                    data={"message": reply_text},
                )
        except BaseException:
            if public_attempt is not None and public_attempt.kind == "send":
                task = asyncio.create_task(
                    finish_meta_outbound_attempt(
                        public_attempt,
                        status="needs_owner_action",
                        safe_reason="provider_call_ambiguous",
                    )
                )
                from services.async_safety_cleanup import await_safety_task

                await await_safety_task(task)
            raise
        if not ok:
            if public_attempt is not None and public_attempt.kind == "send":
                ambiguous = not _provider_rejection_is_definitive(reason)
                try:
                    await finish_meta_outbound_attempt(
                        public_attempt,
                        status="needs_owner_action" if ambiguous else "definitive_failure",
                        safe_reason="accepted_without_provider_id" if ambiguous else "provider_rejected",
                    )
                except BaseException:
                    return CommentReplyResult(status="skipped", reason="ambiguous_needs_owner_action")
                if ambiguous:
                    return CommentReplyResult(status="skipped", reason="ambiguous_needs_owner_action")
            _runtime_logger.error(
                "[meta-comment] reply_failed channel=%s reason=%s",
                binding.channel,
                reason,
            )
            _settle_generated_comment(
                binding=binding,
                comment_id=comment_id,
                inbound_event_id=inbound_event_id,
                accepted=False,
            )
            return CommentReplyResult(status="failed", reason=reason)

        reply_id = str(response.get("id") or "").strip()
        if public_attempt is not None and public_attempt.kind == "send":
            try:
                await finish_meta_outbound_attempt(
                    public_attempt,
                    status="accepted",
                    safe_reason="provider_accepted",
                    provider_message_id=reply_id,
                )
            except BaseException:
                return CommentReplyResult(status="skipped", reason="ambiguous_needs_owner_action")
        _mark_sent_reply(binding, comment_id)
        _settle_generated_comment(
            binding=binding,
            comment_id=comment_id,
            inbound_event_id=inbound_event_id,
            accepted=True,
            reply_id=reply_id,
        )
        _runtime_logger.info(
            "[meta-comment] reply_sent channel=%s tenant=%s asset=%s comment=%s",
            binding.channel,
            binding.tenant_id,
            binding.asset_id[-6:],
            comment_id[-8:],
        )
        return CommentReplyResult(status="sent", reply_id=reply_id)
