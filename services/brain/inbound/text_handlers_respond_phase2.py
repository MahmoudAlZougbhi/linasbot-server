"""Core _process_and_respond phase 2."""

from __future__ import annotations

from typing import Any, cast

from services.brain.ai_reply.ai_reply_turn_runtime import settle_after_outbound, settle_reserved_credits
from services.brain.history_ids import conversation_id_from_user_data, message_id_for_brain
from services.brain.reply.inbound_media import inbound_payload_from_user_data as _inbound_from_user_data

_PHASE_HALT = "_PHASE_HALT"


async def text_handlers_respond_phase2(ctx: dict) -> Any:
    _build_out_of_scope_reply = cast(Any, ctx.get("_build_out_of_scope_reply"))
    _handle_published_cm_runtime = cast(Any, ctx.get("_handle_published_cm_runtime"))
    _is_out_of_business_scope_query = cast(Any, ctx.get("_is_out_of_business_scope_query"))
    current_conversation_id = cast(Any, ctx.get("current_conversation_id"))
    current_gender = cast(Any, ctx.get("current_gender"))
    current_preferred_lang = cast(Any, ctx.get("current_preferred_lang"))
    log_interaction = cast(Any, ctx.get("log_interaction"))
    response_language = cast(Any, ctx.get("response_language"))
    save_conversation_message_to_firestore = cast(Any, ctx.get("save_conversation_message_to_firestore"))
    send_message_func = cast(Any, ctx.get("send_message_func"))
    user_data = cast(Any, ctx.get("user_data"))
    user_id = cast(Any, ctx.get("user_id"))
    user_image_base64 = cast(Any, ctx.get("user_image_base64"))
    user_input_to_process = cast(Any, ctx.get("user_input_to_process"))
    user_name = cast(Any, ctx.get("user_name"))
    if not user_image_base64 and _is_out_of_business_scope_query(user_input_to_process):
        out_of_scope_reply = _build_out_of_scope_reply(current_preferred_lang)
        await send_message_func(user_id, out_of_scope_reply)
        await save_conversation_message_to_firestore(
            user_id,
            "ai",
            out_of_scope_reply,
            current_conversation_id,
            user_name,
            user_data.get("phone_number"),
            metadata={"handled_by": "ai", "source": "out_of_scope_guard"},
        )
        settle_after_outbound(user_data, reply=out_of_scope_reply)
        log_interaction(
            user_id,
            user_input_to_process,
            out_of_scope_reply,
            "out_of_scope_guard",
            user_name=user_name,
            user_phone=user_data.get("phone_number"),
            user_gender=current_gender,
            customer_exists=user_data.get("crm_customer_exists"),
            customer_file_status=user_data.get("customer_file_status"),
            user_data=user_data,
            conversation_id=current_conversation_id,
            handler_path="out_of_scope_guard",
            outcome="restricted_refuse",
            ai_called=False,
            cost_status="none",
            pipeline_decisions=[{"step": "scope_guard", "decision": "out_of_scope_refuse"}],
            flow_steps=[
                {"step": 1, "title": "User → Bot", "content": user_input_to_process},
                {
                    "step": 2,
                    "title": "Out-of-scope guard",
                    "content": "Refused before AI call (clinic scope guard).",
                    "event_type": "restricted_refuse",
                },
                {"step": 3, "title": "Bot → User", "content": out_of_scope_reply, "event_type": "response_sent"},
            ],
        )
        return _PHASE_HALT

    # ===== CM AI CONTROL PLANE — per-tenant published runtime =====
    # Published CM is the SoT when this tenant has an active published version.
    # New tenants without publish get an honest unpublished message (never founder clinic names).
    # No classic GPT fallback. Unpublished tenants get the unpublished message.
    from services.ai_setup.constants import (
        UNPUBLISHED_AI_MESSAGE,
        tenant_allows_legacy_bridge,
        tenant_uses_cm_runtime,
    )

    cm_tenant_id = str(user_data.get("tenant_id") or "").strip()
    if tenant_uses_cm_runtime(cm_tenant_id):
        cm_reply, cm_metadata = await _handle_published_cm_runtime(
            tenant_id=cm_tenant_id,
            message=user_input_to_process,
            detected_language=current_preferred_lang,
            response_language=response_language,
            user_id=str(user_id or ""),
            conversation_id=conversation_id_from_user_data(
                user_data,
                fallback=str(current_conversation_id or user_id or ""),
            ),
            channel=str(user_data.get("channel") or user_data.get("platform") or ""),
            asset_id=str(user_data.get("asset_id") or user_data.get("page_id") or ""),
            provider_display_name=str(user_data.get("display_name") or user_data.get("name") or ""),
            inbound_media=_inbound_from_user_data(user_data, has_image=bool(user_image_base64)),
            attachment_types=list(user_data.get("inbound_attachment_types") or []),
            message_id=message_id_for_brain(user_data),
        )
        # Safe diagnostic view for Testing Lab + Interaction Logs (IDs/titles only).
        cm_diag = {
            "reason": cm_metadata.get("reason"),
            "content_version_id": cm_metadata.get("content_version_id"),
            "index_version_id": cm_metadata.get("index_version_id"),
            "source_ids": list(cm_metadata.get("source_ids") or []),
            "retrieved_sources": list(cm_metadata.get("retrieved_sources") or []),
            "validated": cm_metadata.get("validated"),
            "regenerated": cm_metadata.get("regenerated"),
            "failed_rules": list(cm_metadata.get("failed_rules") or []),
            "blocker": (str(cm_metadata.get("blocker") or "")[:200] or None),
            "exception_class": (str(cm_metadata.get("exception_class") or "")[:80] or None),
        }
        if user_data.get("_dashboard_test_simulation"):
            user_data["_dashboard_cm_diagnostics"] = cm_diag
        if cm_metadata.get("reason") in {"insufficient_credits", "insufficient_messages", "engine_removed"}:
            settle_reserved_credits(user_data)
            return _PHASE_HALT
        active_product_id = str(cm_metadata.get("active_product_id") or "").strip()
        if active_product_id:
            from services.products.outbound_hook import set_pending_product_outbound

            set_pending_product_outbound(user_data, product_id=active_product_id, source="crv2_reply")
        media_delivery = cm_metadata.get("media_delivery") or {}
        if isinstance(media_delivery, dict) and media_delivery.get("ok") and media_delivery.get("items"):
            user_data["_pending_product_media"] = media_delivery
        resource_delivery = cm_metadata.get("resource_delivery") or {}
        if isinstance(resource_delivery, dict) and resource_delivery.get("ok") and resource_delivery.get("items"):
            user_data["_pending_setup_resources"] = resource_delivery
        cm_steps = [
            {
                "step": 1,
                "title": "User → Bot",
                "content": user_input_to_process,
                "event_type": "user_message",
            },
            {
                "step": 2,
                "title": f"CM pipeline ({cm_metadata.get('reason', 'cm_runtime')})",
                "content": (
                    f"Channel route: published CM runtime\n"
                    f"Reason: {cm_metadata.get('reason')}\n"
                    f"Content version: {cm_metadata.get('content_version_id') or 'n/a'}\n"
                    f"Sources: {len(cm_metadata.get('source_ids') or [])}"
                ),
                "event_type": "cm_pipeline",
                "status": "success" if cm_metadata.get("validated", True) else "error",
                "model": cm_metadata.get("model"),
                "tokens": cm_metadata.get("tokens"),
                "cost_usd": cm_metadata.get("cost_usd"),
                "metadata": {
                    "pipeline_decisions": cm_metadata.get("pipeline_decisions"),
                    "ai_called": cm_metadata.get("ai_called"),
                    "blocker": cm_metadata.get("blocker"),
                    "exception_class": cm_metadata.get("exception_class"),
                },
            },
            {
                "step": 3,
                "title": "Bot → User",
                "content": cm_reply,
                "event_type": "response_sent",
            },
        ]
        if not str(cm_reply or "").strip():
            print(
                f"[_process_and_respond] INFO: Brain produced no outbound text "
                f"reason={cm_metadata.get('reason')} — skip empty channel send"
            )
            settle_reserved_credits(user_data)
            log_interaction(
                user_id,
                user_input_to_process,
                "",
                cm_metadata.get("reason", "brain_no_reply"),
                user_name=user_name,
                user_phone=user_data.get("phone_number"),
                user_gender=current_gender,
                customer_exists=user_data.get("crm_customer_exists"),
                customer_file_status=user_data.get("customer_file_status"),
                user_data=user_data,
                conversation_id=current_conversation_id,
                handler_path="cm_runtime_pipeline",
                outcome=cm_metadata.get("reason", "brain_no_reply"),
                pipeline_decisions=list(cm_metadata.get("pipeline_decisions") or []),
                cm_diagnostics=cm_diag,
                ai_called=bool(cm_metadata.get("ai_called")),
                flow_error=(str(cm_metadata.get("blocker") or "")[:200] or None),
                flow_steps=cm_steps,
            )
            return _PHASE_HALT
        await send_message_func(user_id, cm_reply)
        settle_after_outbound(user_data, reply=cm_reply or "", flow_meta=cm_metadata)
        await save_conversation_message_to_firestore(
            user_id,
            "ai",
            cm_reply,
            current_conversation_id,
            user_name,
            user_data.get("phone_number"),
            metadata={
                "handled_by": "cm_runtime_pipeline",
                **{k: v for k, v in cm_metadata.items() if k != "retrieved_sources"},
            },
        )
        log_interaction(
            user_id,
            user_input_to_process,
            cm_reply,
            cm_metadata.get("reason", "cm_runtime"),
            user_name=user_name,
            user_phone=user_data.get("phone_number"),
            user_gender=current_gender,
            customer_exists=user_data.get("crm_customer_exists"),
            customer_file_status=user_data.get("customer_file_status"),
            user_data=user_data,
            conversation_id=current_conversation_id,
            handler_path="cm_runtime_pipeline",
            outcome=cm_metadata.get("reason", "cm_runtime"),
            pipeline_decisions=list(cm_metadata.get("pipeline_decisions") or []),
            cm_diagnostics=cm_diag,
            model=cm_metadata.get("model"),
            tokens=cm_metadata.get("tokens"),
            prompt_tokens=cm_metadata.get("prompt_tokens"),
            completion_tokens=cm_metadata.get("completion_tokens"),
            cost_usd=cm_metadata.get("cost_usd"),
            input_cost_usd=cm_metadata.get("input_cost_usd"),
            output_cost_usd=cm_metadata.get("output_cost_usd"),
            cost_status=cm_metadata.get("cost_status"),
            cost_basis=cm_metadata.get("cost_basis"),
            ai_called=bool(cm_metadata.get("ai_called")),
            token_source="backend" if cm_metadata.get("prompt_tokens") is not None else None,
            flow_error=(str(cm_metadata.get("blocker") or "")[:200] or None),
            flow_steps=cm_steps,
        )
        return _PHASE_HALT

    if not tenant_allows_legacy_bridge(cm_tenant_id):
        lang_key = (response_language or current_preferred_lang or "en").strip().lower()
        if lang_key not in UNPUBLISHED_AI_MESSAGE:
            lang_key = "en" if lang_key == "en" else ("ar" if lang_key in {"ar", "franco"} else "en")
        unpublished_reply = UNPUBLISHED_AI_MESSAGE.get(lang_key) or UNPUBLISHED_AI_MESSAGE["en"]
        await send_message_func(user_id, unpublished_reply)
        settle_after_outbound(user_data, reply=unpublished_reply)
        await save_conversation_message_to_firestore(
            user_id,
            "ai",
            unpublished_reply,
            current_conversation_id,
            user_name,
            user_data.get("phone_number"),
            metadata={"handled_by": "cm_unpublished_guard", "tenant_id": cm_tenant_id},
        )
        log_interaction(
            user_id,
            user_input_to_process,
            unpublished_reply,
            "cm_unpublished",
            user_name=user_name,
            user_phone=user_data.get("phone_number"),
            user_gender=current_gender,
            user_data=user_data,
            conversation_id=current_conversation_id,
            handler_path="cm_unpublished_guard",
            outcome="unpublished",
            ai_called=False,
            cost_status="none",
            flow_steps=[
                {"step": 1, "title": "User → Bot", "content": user_input_to_process},
                {
                    "step": 2,
                    "title": "CM unpublished guard",
                    "content": "Tenant has no published CM version; refused without legacy fallback.",
                    "event_type": "unpublished_refuse",
                },
                {"step": 3, "title": "Bot → User", "content": unpublished_reply, "event_type": "response_sent"},
            ],
        )
        return _PHASE_HALT
    return _PHASE_HALT
