"""Send Brain comment destinations. Private send happens before any public DM claim."""

from __future__ import annotations

from typing import Any

from services.customer_ai.comments.destinations import CommentDestinations
from services.meta_comment_rule_both import (
    _dm_payload,
    _guarded_private_dm,
    _guarded_public_reply,
    _public_payload,
)


async def send_comment_destinations(
    *,
    plan: CommentDestinations,
    binding: Any,
    comment_id: str,
    simulation: bool,
    capture_send: list[dict[str, Any]] | None,
    inbound_event_id: str | None,
    token: str,
    graph_api_version: str,
    client: Any,
    skip_public: bool = False,
) -> Any:
    from services.meta_comment_replies import CommentReplyResult, _mark_sent_reply

    public = "" if skip_public else plan.public_text
    private = plan.private_text
    if plan.public_depends_on_private and not private:
        public = ""
    if not public and not private:
        _settle_comment_send(
            binding=binding,
            comment_id=comment_id,
            inbound_event_id=inbound_event_id,
            reply_id="",
            accepted=False,
        )
        return CommentReplyResult(status="skipped", reason="no_confident_reply")
    rule_id = plan.comment_mode or "brain"

    if simulation:
        if capture_send is not None:
            if private:
                capture_send.append(
                    _dm_payload(comment_id=comment_id, binding=binding, text=private, rule_id=rule_id)
                )
            if public:
                capture_send.append(
                    _public_payload(comment_id=comment_id, binding=binding, text=public, rule_id=rule_id)
                )
        _mark_sent_reply(binding, comment_id)
        _settle_comment_send(
            binding=binding,
            comment_id=comment_id,
            inbound_event_id=inbound_event_id,
            reply_id="simulated",
            accepted=False,
        )
        if public and private:
            return CommentReplyResult(status="simulated_both", reply_id="simulated_both")
        return CommentReplyResult(status="simulated", reply_id="simulated")

    if client is None:
        _settle_comment_send(
            binding=binding,
            comment_id=comment_id,
            inbound_event_id=inbound_event_id,
            reply_id="",
            accepted=False,
        )
        return CommentReplyResult(status="failed", reason="comment_send_client_missing")

    dm_result: dict[str, Any] = {"skipped": True}
    public_result: dict[str, Any] = {"skipped": True}
    if private:
        dm_result = await _guarded_private_dm(
            client=client,
            binding=binding,
            comment_id=comment_id,
            message=private,
            token=token,
            graph_api_version=graph_api_version,
            inbound_event_id=inbound_event_id,
        )
        if plan.public_depends_on_private and not dm_result.get("ok"):
            public = ""
        if dm_result.get("hard_fail") and not public:
            _settle_comment_send(
                binding=binding,
                comment_id=comment_id,
                inbound_event_id=inbound_event_id,
                reply_id="",
                accepted=False,
            )
            return CommentReplyResult(
                status=str(dm_result.get("status") or "failed"),
                reason=str(dm_result.get("reason") or "private_reply_failed"),
            )
    if public:
        public_result = await _guarded_public_reply(
            client=client,
            binding=binding,
            comment_id=comment_id,
            message=public,
            token=token,
            graph_api_version=graph_api_version,
            inbound_event_id=inbound_event_id,
        )
        if public_result.get("hard_fail") and not dm_result.get("ok"):
            _settle_comment_send(
                binding=binding,
                comment_id=comment_id,
                inbound_event_id=inbound_event_id,
                reply_id="",
                accepted=False,
            )
            return CommentReplyResult(
                status=str(public_result.get("status") or "failed"),
                reason=str(public_result.get("reason") or "public_reply_failed"),
            )

    _mark_sent_reply(binding, comment_id)
    public_ok = bool(public_result.get("ok") or public_result.get("skipped") or public_result.get("duplicate"))
    dm_ok = bool(dm_result.get("ok") or dm_result.get("skipped") or dm_result.get("duplicate"))
    reply_id = str(public_result.get("reply_id") or dm_result.get("reply_id") or "")
    if public_ok and dm_ok:
        _settle_comment_send(
            binding=binding,
            comment_id=comment_id,
            inbound_event_id=inbound_event_id,
            reply_id=reply_id,
            accepted=True,
        )
        if public and private:
            return CommentReplyResult(status="sent_comment_and_dm", reply_id=reply_id)
        if private:
            return CommentReplyResult(status="sent_dm", reply_id=reply_id)
        return CommentReplyResult(status="sent", reply_id=reply_id)
    if public_ok:
        _settle_comment_send(
            binding=binding,
            comment_id=comment_id,
            inbound_event_id=inbound_event_id,
            reply_id=reply_id,
            accepted=True,
        )
        return CommentReplyResult(status="sent", reply_id=reply_id, reason="dm_incomplete")
    if dm_ok:
        _settle_comment_send(
            binding=binding,
            comment_id=comment_id,
            inbound_event_id=inbound_event_id,
            reply_id=reply_id,
            accepted=True,
        )
        return CommentReplyResult(status="sent_dm", reply_id=reply_id, reason="public_incomplete")
    _settle_comment_send(
        binding=binding,
        comment_id=comment_id,
        inbound_event_id=inbound_event_id,
        reply_id=reply_id,
        accepted=False,
    )
    return CommentReplyResult(status="failed", reason="comment_and_dm_both_failed")


def _settle_comment_send(
    *,
    binding: Any,
    comment_id: str,
    inbound_event_id: str | None,
    reply_id: str,
    accepted: bool,
) -> None:
    from services.customer_ai.billing import settle_after_send

    tenant_id = str(getattr(binding, "tenant_id", "") or "")
    extras = [
        str(inbound_event_id or ""),
        str(comment_id or ""),
        str(getattr(binding, "conversation_id", "") or ""),
    ]
    settle_after_send(
        tenant_id=tenant_id,
        operation_id=str(comment_id or inbound_event_id or extras[2] or ""),
        accepted=accepted,
        channel="meta_comment",
        provider_message_id=reply_id,
        extra_ids=extras,
    )
