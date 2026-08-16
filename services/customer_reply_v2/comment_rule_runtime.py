"""Apply Comment Rules inside Customer Reply V2 comment turns."""

from __future__ import annotations

from typing import Any

from services.customer_reply_v2.comment_rule_engine import CommentEngineResult, evaluate_published_comment_engine
from services.customer_reply_v2.flags import flags_snapshot
from services.customer_reply_v2.invocation_meter import CustomerTurnMeter, InvocationRecord
from services.customer_reply_v2.models import CustomerReplyOutcome, EvidenceRecord, RetrievalResult


def evaluate_turn_comment_rules(
    *,
    tenant_id: str,
    comment_text: str,
    channel: str,
    post_id: str,
    account_id: str,
    channel_capabilities: dict[str, Any] | None = None,
) -> CommentEngineResult:
    return evaluate_published_comment_engine(
        tenant_id,
        comment_text=comment_text,
        channel=channel,
        post_id=post_id,
        account_id=account_id,
    )


def deterministic_rule_outcome(
    *,
    engine: CommentEngineResult,
    meter: CustomerTurnMeter,
    channel_meta: dict[str, Any],
    channel_capabilities: dict[str, Any] | None = None,
) -> CustomerReplyOutcome:
    caps = dict(channel_capabilities or (channel_meta or {}).get("channel_capabilities") or {})
    action = engine.action
    needs_public = action in {
        "reply_comment_static",
        "reply_comment",
        "reply_comment_and_dm_static",
        "reply_comment_and_dm",
    }
    needs_dm = action in {"send_dm_static", "reply_dm", "reply_comment_and_dm_static", "reply_comment_and_dm"}
    diagnostic = ""
    if needs_public and not caps.get("can_reply_publicly", True):
        diagnostic = "channel_cannot_reply_publicly"
    if needs_dm and not caps.get("can_send_dm", True):
        diagnostic = diagnostic or "channel_cannot_send_dm"
    meter.record(
        InvocationRecord(
            operation="comment_rule_deterministic",
            is_ai=False,
            success=not bool(diagnostic),
            failure_stage=diagnostic or None,
        )
    )
    reply = None if action == "ignore" or diagnostic else (engine.reply_text or engine.dm_text or None)
    return CustomerReplyOutcome(
        stop=True,
        reply=reply,
        reason="comment_rule_capability_denied"
        if diagnostic
        else ("comment_rule_ignore" if action == "ignore" else "comment_rule_deterministic"),
        evidence_status="policy_stop",
        metadata={
            "ai_called": False,
            "cost_status": "none",
            "comment_rule_scope": engine.scope,
            "comment_rule_id": engine.rule_id,
            "comment_rule_mode": "deterministic",
            "comment_rule_action": action,
            "comment_rule_revision": engine.rule_revision,
            "comment_rule_trigger": engine.trigger_matched,
            "owner_diagnostic": diagnostic,
            "channel_metadata": channel_meta,
            "metering": meter.to_public_dict(),
            "flags": flags_snapshot(),
            "resource_delivery": _deterministic_resources(engine, channel_meta),
        },
    )


def _deterministic_resources(engine: CommentEngineResult, channel_meta: dict[str, Any]) -> dict[str, Any]:
    from services.customer_reply_v2.resource_actions import resolve_resource_actions

    refs = []
    for att in list(engine.attachments or []):
        if not isinstance(att, dict):
            continue
        ref = str(att.get("id") or "").strip()
        if ref:
            refs.append({"action": "send_resource", "resource_ref": ref})
    if not refs:
        return {"ok": True, "items": [], "ai_charged": False, "claimed_sent": False}
    tenant_id = str((channel_meta or {}).get("tenant_id") or "")
    if not tenant_id:
        return {"ok": True, "items": refs, "ai_charged": False, "claimed_sent": False, "pending_send": True}
    return resolve_resource_actions(
        tenant_id=tenant_id,
        actions=refs,
        allowed_source_ids=[f"comments:{engine.rule_id}"] if engine.rule_id else None,
        channel_capabilities={"max_media_items": 8},
    )


def engine_trace_fields(engine: CommentEngineResult) -> dict[str, Any]:
    return {
        "comment_rule_scope": engine.scope,
        "comment_rule_id": engine.rule_id,
        "comment_rule_mode": engine.rule_mode,
        "comment_rule_action": engine.action,
        "comment_rule_revision": engine.rule_revision,
        "comment_rule_trigger": engine.trigger_matched,
        "comment_rule_conflict": engine.conflict_event,
        "ai_guidance_comment_rules": engine.ai_guidance_rules,
    }


def merge_applicable_comment_rules(
    retrieval: RetrievalResult,
    engine: CommentEngineResult,
    *,
    published_revision: str,
) -> RetrievalResult:
    """Configured applicable AI-guidance rules are evidence. They do not replace business retrieval."""
    if engine.rule_mode != "ai_guidance" or not engine.ai_guidance_rules:
        return retrieval
    existing = {e.source_id for e in retrieval.evidence}
    extra: list[EvidenceRecord] = []
    from services.cm.setup_resources import descriptors_for_item

    for row in engine.ai_guidance_rules:
        rule_id = str(row.get("id") or "").strip()
        if not rule_id:
            continue
        source_id = f"comments:{rule_id}"
        if source_id in existing:
            continue
        post_ids = [str(x).strip() for x in (row.get("post_ids") or []) if str(x).strip()]
        extra.append(
            EvidenceRecord(
                source_id=source_id,
                section_id="comments",
                title=str(row.get("title") or rule_id),
                content=(
                    f"Comment Rule (AI guidance, not business knowledge). "
                    f"scope={row.get('scope') or ''} action={row.get('ai_action_mode') or ''} "
                    f"post_id={row.get('post_id') or ''} post_ids={','.join(post_ids)}\n"
                    f"{str(row.get('ai_instructions') or '').strip()}"
                ),
                published_revision=published_revision,
                allowed_resources=descriptors_for_item(source_item_id=source_id, item=row),
            )
        )
        existing.add(source_id)
    if not extra:
        return retrieval
    retrieval.evidence = extra + list(retrieval.evidence)
    for rec in extra:
        if rec.source_id not in retrieval.selected_source_ids:
            retrieval.selected_source_ids = [rec.source_id, *retrieval.selected_source_ids]
        if rec.section_id not in retrieval.selected_section_ids:
            retrieval.selected_section_ids = ["comments", *retrieval.selected_section_ids]
    return retrieval
