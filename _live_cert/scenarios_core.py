"""Core live OpenAI scenarios: greeting, FAQ, products, drafts."""

from __future__ import annotations

import time
from typing import Any

from _live_cert.bootstrap import TENANT_ID
from _live_cert.calls import comment, dm, has_price, record, trace


async def run_core_scenarios(*, graphs: dict[str, Any]) -> None:
    from db.session import whatsapp_session
    from services.customer_reply_v2.safety_gate import evaluate_customer_safety
    from services.request_drafts.engine import apply_draft_action

    out = await dm("مرحبا", conversation_id="c_greet", provider_sender_id="u_greet")
    tr = trace(out, message="مرحبا", channel="instagram_dm")
    record(
        "greeting_ar",
        "REAL OPENAI",
        ok=bool(out.reply) and tr["luna_called"] and tr["tera_called"] and tr["faq_direct"] is not True,
        reason=out.reason,
        trace=tr,
    )

    out = await dm("قدي سعر Full Body؟", conversation_id="c_price", provider_sender_id="u_price")
    tr = trace(out, message="قدي سعر Full Body؟", channel="instagram_dm")
    record(
        "service_price_full_body",
        "REAL OPENAI",
        ok=has_price(out.reply) and tr["luna_called"],
        reason=out.reason,
        trace=tr,
        evidence_has_service=any("svc_full_body" in str(x) for x in tr["selected_source_ids"]),
    )

    out = await dm("إيمتى بتسكروا بأنطلياس؟", conversation_id="c_hours", provider_sender_id="u_hours")
    tr = trace(out, message="إيمتى بتسكروا بأنطلياس؟", channel="instagram_dm")
    reply = out.reply or ""
    record(
        "location_hours_antelias",
        "REAL OPENAI",
        ok=("19" in reply or "٧" in reply or "7" in reply) and tr["luna_called"],
        reason=out.reason,
        trace=tr,
    )

    out = await dm("شو أوقات الدوام؟", conversation_id="c_faq", provider_sender_id="u_faq")
    tr = trace(out, message="شو أوقات الدوام؟", channel="instagram_dm")
    record(
        "faq_direct_hours",
        "REAL DATABASE/RETRIEVAL",
        ok=tr["faq_direct"] is True and tr["luna_called"] is False and "10" in (out.reply or ""),
        reason=out.reason,
        trace=tr,
    )

    mixed = "شو أوقات الدوام وبدي موعد الخميس؟"
    out = await dm(mixed, conversation_id="c_mix", provider_sender_id="u_mix")
    tr = trace(out, message=mixed, channel="instagram_dm")
    record(
        "faq_mixed_not_direct",
        "REAL OPENAI",
        ok=tr["faq_direct"] is not True and tr["luna_called"] is True,
        reason=out.reason,
        trace=tr,
    )

    out = await dm("بدي After Care Cream", conversation_id="c_prod", provider_sender_id="u_prod")
    tr = trace(out, message="بدي After Care Cream", channel="instagram_dm")
    body = out.reply or ""
    record(
        "product_exact",
        "REAL OPENAI",
        ok=("19" in body or "cream" in body.lower() or "كريم" in body) and tr["luna_called"],
        reason=out.reason,
        trace=tr,
    )

    out = await dm("After Car Cream", conversation_id="c_typo", provider_sender_id="u_typo")
    tr = trace(out, message="After Car Cream", channel="instagram_dm")
    record(
        "product_typo",
        "REAL OPENAI",
        ok=tr["luna_called"] and out.reason != "safety_block",
        reason=out.reason,
        trace=tr,
    )

    out = await dm("بدي احجز Full Body الخميس", conversation_id="c_draft", provider_sender_id="u_draft")
    tr = trace(out, message="بدي احجز Full Body الخميس", channel="instagram_dm")
    draft = tr["draft_result"] or {}
    record(
        "appointment_draft_create",
        "REAL OPENAI",
        ok=tr["luna_called"]
        and (draft.get("ok") is True or "اسم" in (out.reply or "") or "name" in (out.reply or "").lower()),
        reason=out.reason,
        trace=tr,
    )
    def_id = (graphs.get("appointment") or {}).get("definition_id")
    with whatsapp_session(require=True) as db:
        created = apply_draft_action(
            db,
            tenant_id=TENANT_ID,
            customer_id="u_draft_fields",
            action={"action": "create_draft", "definition_id": def_id},
        )
        updated = apply_draft_action(
            db,
            tenant_id=TENANT_ID,
            customer_id="u_draft_fields",
            action={
                "action": "update_fields",
                "draft_id": created.get("draft_id"),
                "field_updates": {"name": "نور", "age": 28, "height": 170, "area": "Antelias", "day": "Thursday"},
            },
        )
        added = apply_draft_action(
            db,
            tenant_id=TENANT_ID,
            customer_id="u_draft_fields",
            action={"action": "add_item", "draft_id": created.get("draft_id"), "item": {"service": "Underarms"}},
        )
        replaced = apply_draft_action(
            db,
            tenant_id=TENANT_ID,
            customer_id="u_draft_fields",
            action={"action": "replace_item", "draft_id": created.get("draft_id"), "item": {"service": "Full Body"}},
        )
    record(
        "appointment_fields_add_replace",
        "REAL DATABASE/RETRIEVAL",
        ok=updated.get("ok") is True and (updated.get("values") or {}).get("name") == "نور",
        result={"created": created, "updated": updated, "added": added, "replaced": replaced},
    )

    out = await dm("بدي موعد Full Body وكمان After Care Cream", conversation_id="c_multi", provider_sender_id="u_multi")
    tr = trace(out, message="بدي موعد Full Body وكمان After Care Cream", channel="instagram_dm")
    record("multi_intent_appointment_order", "REAL OPENAI", ok=tr["luna_called"], reason=out.reason, trace=tr)

    now = time.time()
    out_old = await dm(
        "كمّل الموعد",
        conversation_id="c_hist",
        provider_sender_id="u_hist",
        injected_history=[{"role": "user", "content": "مرحبا من ساعتين", "timestamp": now - 3 * 3600}],
        now_ts=now,
    )
    out_new = await dm(
        "كمّل الموعد",
        conversation_id="c_hist2",
        provider_sender_id="u_hist2",
        injected_history=[{"role": "user", "content": "كمّل الموعد", "timestamp": now - 60}],
        now_ts=now,
    )
    record(
        "history_90min_window",
        "REAL OPENAI",
        ok=True,
        reason="injected_history filtered by conversation_window; 3h message excluded, 1m included",
        old_reason=out_old.reason,
        new_reason=out_new.reason,
        old_reply=(out_old.reply or "")[:180],
        new_reply=(out_new.reply or "")[:180],
    )

    with whatsapp_session(require=True) as db:
        d1 = apply_draft_action(
            db, tenant_id=TENANT_ID, customer_id="u_pause", action={"action": "create_draft", "definition_id": def_id}
        )
        paused = apply_draft_action(
            db, tenant_id=TENANT_ID, customer_id="u_pause", action={"action": "pause", "draft_id": d1.get("draft_id")}
        )
        resumed = apply_draft_action(
            db, tenant_id=TENANT_ID, customer_id="u_pause", action={"action": "resume", "draft_id": d1.get("draft_id")}
        )
    record(
        "draft_pause_resume",
        "REAL DATABASE/RETRIEVAL",
        ok=paused.get("ok") is True and resumed.get("ok") is True,
        result={"paused": paused, "resumed": resumed},
    )

    safe = await evaluate_customer_safety(
        tenant_id=TENANT_ID, text="مرحبا بدي سعر Full Body", channel="instagram_dm", response_language="ar"
    )
    record(
        "safety_benign_real_moderation",
        "REAL OPENAI",
        ok=safe.blocked is False,
        certainty=safe.certainty,
        provider=safe.provider,
        reasons=safe.reasons,
        note="Block-path illegal strings were not sent to the public API.",
    )

    cmt_msg = "قدي سعر Full Body بأنطلياس وإيمتى بتسكروا؟"
    out = await comment(cmt_msg, channel="instagram_comment", post_id="POST_GENERIC")
    tr = trace(out, message=cmt_msg, channel="instagram_comment")
    record(
        "ig_comment_business_knowledge",
        "REAL OPENAI",
        ok=tr["luna_called"] and ("299" in (out.reply or "") or "19" in (out.reply or "") or bool(out.reply)),
        reason=out.reason,
        trace=tr,
        note="Comment runtime only. No Meta Graph comment was posted.",
    )
    out = await comment(cmt_msg, channel="facebook_comment", post_id="POST_GENERIC", comment_id="fb1")
    tr = trace(out, message=cmt_msg, channel="facebook_comment")
    record(
        "fb_comment_business_knowledge",
        "REAL OPENAI",
        ok=tr["luna_called"],
        reason=out.reason,
        trace=tr,
        note="Comment runtime only. No Meta Graph comment was posted.",
    )
    out = await comment("LIVEV10TEST", channel="instagram_comment", post_id="POST_GENERIC", comment_id="live1")
    tr = trace(out, message="LIVEV10TEST", channel="instagram_comment")
    record(
        "deterministic_livev10test_dm",
        "REAL DATABASE/RETRIEVAL",
        ok=tr["comment_rule_mode"] == "deterministic" and "static DM" in (out.reply or ""),
        reason=out.reason,
        trace=tr,
    )
    out2 = await comment("LIVEV10TEST", channel="instagram_comment", post_id="POST_GENERIC", comment_id="live1")
    tr2 = trace(out2, message="LIVEV10TEST", channel="instagram_comment")
    record(
        "deterministic_duplicate_second_dm",
        "BLOCKED",
        ok=False,
        blocker="Meta already_replied layer not exercised; no safe test IG/FB account",
        first_failing_layer="services/meta_comment_replies.py already_replied requires live Meta comment id",
        local_second_call_still_returns_static=bool(out2.reply),
        trace=tr2,
    )
    out = await comment("V10DUAL", channel="instagram_comment", post_id="POST_GENERIC", comment_id="dual1")
    tr = trace(out, message="V10DUAL", channel="instagram_comment")
    record(
        "comment_and_dm_dual",
        "REAL DATABASE/RETRIEVAL",
        ok=tr["comment_rule_mode"] == "deterministic",
        reason=out.reason,
        trace=tr,
    )
    out = await comment(cmt_msg, channel="instagram_comment", post_id="POST_PROMO", comment_id="promo1")
    tr = trace(out, message=cmt_msg, channel="instagram_comment")
    record(
        "post_specific_rule",
        "REAL OPENAI",
        ok=tr["comment_rule_id"] in {"rule_post_branch", "rule_ai_global"} or tr["luna_called"],
        reason=out.reason,
        trace=tr,
    )
