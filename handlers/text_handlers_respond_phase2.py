"""Core _process_and_respond phase 2."""

from __future__ import annotations

from typing import Any, cast

import config
from services.customer_reply_v2.inbound_media import inbound_payload_from_user_data as _inbound_from_user_data

_PHASE_HALT = "_PHASE_HALT"


async def text_handlers_respond_phase2(ctx: dict) -> Any:
    _build_out_of_scope_reply = cast(Any, ctx.get("_build_out_of_scope_reply"))
    _ge = cast(Any, ctx.get("_ge"))
    _handle_published_cm_runtime = cast(Any, ctx.get("_handle_published_cm_runtime"))
    _is_out_of_clinic_scope_query = cast(Any, ctx.get("_is_out_of_clinic_scope_query"))
    current_conversation_id = cast(Any, ctx.get("current_conversation_id"))
    current_gender = cast(Any, ctx.get("current_gender"))
    current_preferred_lang = cast(Any, ctx.get("current_preferred_lang"))
    get_gender_from_message = cast(Any, ctx.get("get_gender_from_message"))
    log_interaction = cast(Any, ctx.get("log_interaction"))
    response_language = cast(Any, ctx.get("response_language"))
    router_route = cast(Any, ctx.get("router_route"))
    save_conversation_message_to_firestore = cast(Any, ctx.get("save_conversation_message_to_firestore"))
    send_message_func = cast(Any, ctx.get("send_message_func"))
    user_data = cast(Any, ctx.get("user_data"))
    user_id = cast(Any, ctx.get("user_id"))
    user_image_base64 = cast(Any, ctx.get("user_image_base64"))
    user_input_to_process = cast(Any, ctx.get("user_input_to_process"))
    user_name = cast(Any, ctx.get("user_name"))
    user_persistence = cast(Any, ctx.get("user_persistence"))
    if not user_image_base64 and _is_out_of_clinic_scope_query(user_input_to_process):
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
    # New tenants without publish get an honest unpublished message (never Marwa/Linas).
    # Temporary legacy bridge: only ``linas`` without published content (removed in Wave 6).
    from services.cm.constants import (
        DEFAULT_TENANT_ID,
        UNPUBLISHED_AI_MESSAGE,
        tenant_allows_legacy_bridge,
        tenant_uses_cm_runtime,
    )

    cm_tenant_id = user_data.get("tenant_id") or DEFAULT_TENANT_ID
    if tenant_uses_cm_runtime(cm_tenant_id):
        cm_reply, cm_metadata = await _handle_published_cm_runtime(
            tenant_id=cm_tenant_id,
            message=user_input_to_process,
            detected_language=current_preferred_lang,
            response_language=response_language,
            user_id=str(user_id or ""),
            conversation_id=str(user_data.get("conversation_id") or user_data.get("active_conversation_id") or ""),
            channel=str(user_data.get("channel") or user_data.get("platform") or ""),
            asset_id=str(user_data.get("asset_id") or user_data.get("page_id") or ""),
            provider_display_name=str(user_data.get("display_name") or user_data.get("name") or ""),
            inbound_media=_inbound_from_user_data(user_data),
            attachment_types=list(user_data.get("inbound_attachment_types") or []),
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
        }
        if user_data.get("_dashboard_test_simulation"):
            user_data["_dashboard_cm_diagnostics"] = cm_diag
        if cm_metadata.get("reason") == "insufficient_credits":
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
                },
            },
            {
                "step": 3,
                "title": "Bot → User",
                "content": cm_reply,
                "event_type": "response_sent",
            },
        ]
        await send_message_func(user_id, cm_reply)
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
            flow_steps=cm_steps,
        )
        return _PHASE_HALT

    if not tenant_allows_legacy_bridge(cm_tenant_id):
        lang_key = (response_language or current_preferred_lang or "en").strip().lower()
        if lang_key not in UNPUBLISHED_AI_MESSAGE:
            lang_key = "en" if lang_key == "en" else ("ar" if lang_key in {"ar", "franco"} else "en")
        unpublished_reply = UNPUBLISHED_AI_MESSAGE.get(lang_key) or UNPUBLISHED_AI_MESSAGE["en"]
        await send_message_func(user_id, unpublished_reply)
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
    # =====================================================================

    # ===== AI SMART EMPLOYEE: ROUTER (Phase 2, 10) =====
    # Long one-line messages often include gender («ana shab», «شاب», etc.). Infer before router/GPT
    # so runtime context and router do not ask again. Full user_input_to_process is still sent to GPT unchanged.
    if current_gender == "unknown" and (user_input_to_process or "").strip():
        _ginf = get_gender_from_message(user_input_to_process)
        if _ginf in ("male", "female"):
            config.user_gender[user_id] = _ginf
            current_gender = _ginf
            if config.user_greeting_stage.get(user_id, 0) < 2:
                config.user_greeting_stage[user_id] = 2
            try:
                await user_persistence.save_user_gender(
                    user_id,
                    _ginf,
                    phone=user_data.get("phone_number", user_id),
                    name=user_name,
                )
            except Exception as _ge:
                print(f"⚠️ save_user_gender (pre-router infer): {_ge}")
            print(f"[_process_and_respond] ✅ Gender inferred from full message (pre-router): {_ginf}")

    config.ensure_conversation_state(user_data)
    conv_state = config.get_conversation_state(user_id, user_data)
    ai_primary_mode = bool(getattr(config, "AI_PRIMARY_ORCHESTRATION", True))
    router_action = router_route(user_id, user_input_to_process, conv_state)
    if ai_primary_mode:
        router_action = None

    # Phase 12: Debugging/logging (Plan §18)
    print("[_process_and_respond] 📋 ORCHESTRATION LOG:")
    print(f"   - normalized_input_len={len((user_input_to_process or '').strip())}")
    print(
        f"   - state_before: gender={conv_state.get('gender')}, awaiting_gender={conv_state.get('awaiting_gender')}, awaiting_clarification={conv_state.get('awaiting_clarification')}, original_question={bool(conv_state.get('original_question'))}"
    )
    print(f"   - ai_primary_mode: {ai_primary_mode}")
    print(f"   - detected_action: {router_action if router_action else 'ai_decides'}")
    _pack = [
        "DEFAULT_TENANT_ID",
        "UNPUBLISHED_AI_MESSAGE",
        "_build_out_of_scope_reply",
        "_ge",
        "_ginf",
        "_handle_published_cm_runtime",
        "_is_out_of_clinic_scope_query",
        "ai_primary_mode",
        "cm_diag",
        "cm_metadata",
        "cm_reply",
        "cm_steps",
        "cm_tenant_id",
        "conv_state",
        "current_conversation_id",
        "current_gender",
        "current_preferred_lang",
        "get_gender_from_message",
        "k",
        "lang_key",
        "log_interaction",
        "out_of_scope_reply",
        "response_language",
        "router_action",
        "router_route",
        "save_conversation_message_to_firestore",
        "send_message_func",
        "tenant_allows_legacy_bridge",
        "tenant_uses_cm_runtime",
        "unpublished_reply",
        "user_data",
        "user_id",
        "user_image_base64",
        "user_input_to_process",
        "user_name",
        "user_persistence",
        "v",
    ]
    for _k in _pack:
        if _k in locals():
            ctx[_k] = locals()[_k]
    return None
