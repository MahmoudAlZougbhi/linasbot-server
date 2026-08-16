"""Deterministic comment+DM rule handling (simulation + live independent HA sends)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, TypeGuard

from services.cm.comment_rules import CommentRuleDecision
from services.meta_app_registry import MetaAssetBinding

if TYPE_CHECKING:
    from services.meta_comment_replies import CommentReplyResult

_runtime_logger = logging.getLogger("uvicorn.error")


def _public_payload(*, comment_id: str, binding: MetaAssetBinding, text: str, rule_id: str) -> dict[str, Any]:
    return {
        "comment_id": comment_id,
        "channel": binding.channel,
        "message": text,
        "delivery": "public_reply",
        "rule_id": rule_id,
    }


def _dm_payload(*, comment_id: str, binding: MetaAssetBinding, text: str, rule_id: str) -> dict[str, Any]:
    return {
        "comment_id": comment_id,
        "channel": binding.channel,
        "message": text,
        "delivery": "private_reply",
        "rule_id": rule_id,
    }


def is_deterministic_comment_and_dm(rule_decision: Any) -> TypeGuard[CommentRuleDecision]:
    return (
        rule_decision is not None
        and getattr(rule_decision, "action", "") == "reply_comment_and_dm"
        and getattr(rule_decision, "rule_mode", "") == "deterministic"
    )


async def maybe_handle_comment_and_dm(
    *,
    rule_decision: CommentRuleDecision,
    binding: MetaAssetBinding,
    comment_id: str,
    simulation: bool,
    capture_send: list[dict[str, Any]] | None,
    inbound_event_id: str | None = None,
    token: str = "",
    graph_api_version: str = "v24.0",
    client: Any | None = None,
    skip_public: bool = False,
) -> CommentReplyResult:
    """Send public comment + private DM with separate outbound purposes, or simulate both."""
    from services.meta_comment_replies import CommentReplyResult, _mark_sent_reply

    public_text = (rule_decision.reply_text or "").strip()
    dm_text = (rule_decision.dm_text or "").strip()
    if simulation:
        if capture_send is not None:
            if public_text and not skip_public:
                capture_send.append(
                    _public_payload(
                        comment_id=comment_id,
                        binding=binding,
                        text=public_text,
                        rule_id=rule_decision.rule_id,
                    )
                )
            if dm_text:
                capture_send.append(
                    _dm_payload(comment_id=comment_id, binding=binding, text=dm_text, rule_id=rule_decision.rule_id)
                )
        _mark_sent_reply(binding, comment_id)
        from services.meta_comment_resource_send import send_comment_rule_resources

        await send_comment_rule_resources(
            tenant_id=binding.tenant_id,
            rule_decision=rule_decision,
            comment_id=comment_id,
            channel=binding.channel,
            binding_id=binding.binding_id,
            simulation=True,
            capture_send=capture_send,
        )
        return CommentReplyResult(status="simulated_both", reply_id="simulated_both")

    if client is None:
        return CommentReplyResult(status="failed", reason="comment_and_dm_client_missing")

    public_result = {"skipped": True}
    dm_result = {"skipped": True}
    if public_text and not skip_public:
        public_result = await _guarded_public_reply(
            client=client,
            binding=binding,
            comment_id=comment_id,
            message=public_text,
            token=token,
            graph_api_version=graph_api_version,
            inbound_event_id=inbound_event_id,
        )
        if public_result.get("hard_fail"):
            return CommentReplyResult(
                status=str(public_result.get("status") or "failed"),
                reason=str(public_result.get("reason") or "public_reply_failed"),
            )
    if dm_text:
        dm_result = await _guarded_private_dm(
            client=client,
            binding=binding,
            comment_id=comment_id,
            message=dm_text,
            token=token,
            graph_api_version=graph_api_version,
            inbound_event_id=inbound_event_id,
        )
        if dm_result.get("hard_fail") and not public_result.get("ok"):
            return CommentReplyResult(
                status=str(dm_result.get("status") or "failed"),
                reason=str(dm_result.get("reason") or "private_reply_failed"),
            )

    _mark_sent_reply(binding, comment_id)
    public_ok = bool(public_result.get("ok") or public_result.get("skipped") or public_result.get("duplicate"))
    dm_ok = bool(dm_result.get("ok") or dm_result.get("skipped") or dm_result.get("duplicate"))
    from services.meta_comment_resource_send import send_comment_rule_resources

    await send_comment_rule_resources(
        tenant_id=binding.tenant_id,
        rule_decision=rule_decision,
        comment_id=comment_id,
        channel=binding.channel,
        binding_id=binding.binding_id,
        simulation=False,
        capture_send=None,
    )
    reply_id = str(public_result.get("reply_id") or dm_result.get("reply_id") or "")
    if public_ok and dm_ok:
        return CommentReplyResult(status="sent_comment_and_dm", reply_id=reply_id)
    if public_ok:
        return CommentReplyResult(status="sent", reply_id=reply_id, reason="dm_incomplete")
    if dm_ok:
        return CommentReplyResult(status="sent_dm", reply_id=reply_id, reason="public_incomplete")
    return CommentReplyResult(status="failed", reason="comment_and_dm_both_failed")


apply_comment_and_dm_rule = maybe_handle_comment_and_dm


async def _guarded_public_reply(
    *,
    client: Any,
    binding: MetaAssetBinding,
    comment_id: str,
    message: str,
    token: str,
    graph_api_version: str,
    inbound_event_id: str | None,
) -> dict[str, Any]:
    from services.meta_comment_replies import _graph_post_form, _provider_rejection_is_definitive
    from services.meta_graph_routing import graph_api_url

    path = f"{comment_id}/comments" if binding.channel == "facebook" else f"{comment_id}/replies"

    async def _send() -> dict[str, Any]:
        ok, reason, response = await _graph_post_form(
            client,
            graph_api_url(binding, graph_api_version=graph_api_version, path=path),
            token=token,
            data={"message": message},
        )
        if not ok:
            status = 400 if str(reason).startswith("http_4") or str(reason).startswith("graph_http_4") else 0
            return {"success": False, "error": reason, "status_code": status or None}
        reply_id = str(response.get("id") or "").strip()
        if not reply_id:
            return {"success": False, "provider": "meta", "error": "meta_send_missing_message_id"}
        return {"success": True, "provider": "meta", "message_id": reply_id}

    return await _run_guarded(
        send=_send,
        inbound_event_id=inbound_event_id,
        binding=binding,
        purpose="primary_reply",
        fail_prefix="public_reply",
        definitive=_provider_rejection_is_definitive,
    )


async def _guarded_private_dm(
    *,
    client: Any,
    binding: MetaAssetBinding,
    comment_id: str,
    message: str,
    token: str,
    graph_api_version: str,
    inbound_event_id: str | None,
) -> dict[str, Any]:
    from services.meta_comment_private_reply import send_comment_private_reply
    from services.meta_comment_replies import _provider_rejection_is_definitive

    async def _send() -> dict[str, Any]:
        ok, reason, response = await send_comment_private_reply(
            client,
            binding=binding,
            comment_id=comment_id,
            message=message,
            token=token,
            graph_api_version=graph_api_version,
        )
        if not ok:
            status = 400 if "graph_http_4" in str(reason) or str(reason).startswith("http_4") else 0
            return {"success": False, "error": reason, "status_code": status or None}
        reply_id = str(response.get("id") or response.get("message_id") or "").strip()
        if not reply_id:
            return {"success": False, "provider": "meta", "error": "meta_send_missing_message_id"}
        return {"success": True, "provider": "meta", "message_id": reply_id}

    return await _run_guarded(
        send=_send,
        inbound_event_id=inbound_event_id,
        binding=binding,
        purpose="comment_private_dm",
        fail_prefix="private_reply",
        definitive=_provider_rejection_is_definitive,
    )


async def _run_guarded(
    *,
    send: Any,
    inbound_event_id: str | None,
    binding: MetaAssetBinding,
    purpose: str,
    fail_prefix: str,
    definitive: Any,
) -> dict[str, Any]:
    from services.ai_reply_delivery import classify_send_result
    from services.meta_controlled_evidence import meta_evidence_surface
    from services.meta_outbound_attempts import execute_guarded_meta_send

    if inbound_event_id:
        result = await execute_guarded_meta_send(
            event_id=inbound_event_id,
            surface=meta_evidence_surface(kind="meta_comment", channel=binding.channel),
            binding_id=binding.binding_id,
            purpose=purpose,
            send=send,
        )
    else:
        result = await send()
    evidence = classify_send_result(result)
    if evidence.get("duplicate_suppressed"):
        return {"ok": True, "duplicate": True, "reply_id": ""}
    if evidence.get("needs_owner_action"):
        _runtime_logger.warning("[meta-comment] %s_needs_owner_action purpose=%s", fail_prefix, purpose)
        return {"ok": False, "hard_fail": True, "status": "skipped", "reason": "ambiguous_needs_owner_action"}
    if evidence.get("success"):
        return {"ok": True, "reply_id": str(evidence.get("provider_message_id") or "")}
    err = str((result or {}).get("error") if isinstance(result, dict) else "") or str(evidence.get("reason") or "")
    hard = bool(evidence.get("permanent_block")) or definitive(err)
    return {
        "ok": False,
        "hard_fail": hard,
        "status": "failed" if not hard else "failed",
        "reason": f"{fail_prefix}:{err}" if err else fail_prefix,
    }
