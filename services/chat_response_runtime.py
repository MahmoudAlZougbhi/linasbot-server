"""Orchestrator for legacy get_bot_chat_response."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from services.chat_response_runtime_common import (
    json,
)
from services.chat_response_runtime_finish import finish_chat_response
from services.chat_response_runtime_gpt import call_first_gpt
from services.chat_response_runtime_post import postprocess_chat_response
from services.chat_response_runtime_prepare import prepare_chat_response_identity
from services.chat_response_runtime_prompt import prepare_chat_response_prompt
from services.chat_response_runtime_tool_loop import run_tool_loop


async def get_bot_chat_response(
    user_id: str,
    user_input: str,
    current_context_messages: list,
    current_gender: str,
    current_preferred_lang: str,
    response_language: str,
    is_initial_message_after_start: bool,
    initial_user_query_to_process: str | None = None,
    custom_knowledge_context: str | None = None,
    operational_context: str | None = None,
    last_ai_response_at: Any = None,
    user_image_base64: str | None = None,
    user_image_format: str = "jpeg",
) -> dict:
    ns = SimpleNamespace()
    ns.user_id = user_id
    ns.user_input = user_input
    ns.current_context_messages = current_context_messages
    ns.current_gender = current_gender
    ns.current_preferred_lang = current_preferred_lang
    ns.response_language = response_language
    ns.is_initial_message_after_start = is_initial_message_after_start
    ns.initial_user_query_to_process = initial_user_query_to_process
    ns.custom_knowledge_context = custom_knowledge_context
    ns.operational_context = operational_context
    ns.last_ai_response_at = last_ai_response_at
    ns.user_image_base64 = user_image_base64
    ns.user_image_format = user_image_format
    ns.gpt_raw_content = ""
    ns.selected_model = None
    ns.final_response_model_used = None
    ns.flow_ai_query_summary = ""
    ns.flow_bot_sent_to_ai_full = ""
    ns.flow_customer_context_sent = None
    early = await prepare_chat_response_identity(ns)
    if early is not None:
        return early
    early = await prepare_chat_response_prompt(ns)
    if early is not None:
        return early
    try:
        early = await call_first_gpt(ns)
        if early is not None:
            return early
        early = await run_tool_loop(ns)
        if early is not None:
            return early
        early = await postprocess_chat_response(ns)
        if early is not None:
            return early
        early = await finish_chat_response(ns)
        if early is not None:
            return early
        return ns.parsed_response
    except json.JSONDecodeError as e:
        print(f"â‌Œ JSON Decode Error from GPT chat response: {e}. Raw content: {ns.gpt_raw_content}")
        # NEW: Try to parse a potential plain text reply if JSON fails
        ns.generic_error_by_lang = {
            "ar": "عذراً، صار خطأ تقني وأنا عم عالج طلبك. جرّب مرة ثانية بعد شوي أو تواصل معنا مباشرة.",
            "en": "Sorry, I encountered a technical issue while understanding your request. Please try again shortly or contact our staff directly.",
            "fr": "Désolé, j'ai rencontré un problème technique en traitant votre demande. Veuillez réessayer dans un instant ou contacter notre équipe.",
            "franco": "عذراً، صار خطأ تقني وأنا عم عالج طلبك. جرّب مرة ثانية بعد شوي أو تواصل معنا مباشرة.",
        }
        ns.fallback_bot_reply = (
            ns.gpt_raw_content
            if ns.gpt_raw_content
            else ns.generic_error_by_lang.get(ns.current_preferred_lang, ns.generic_error_by_lang["en"])
        )
        return {
            "action": "unknown_query",
            "bot_reply": ns.fallback_bot_reply,
            "detected_language": ns.current_preferred_lang,
            "current_gender_from_config": ns.current_gender,  # Pass the actual gender from config
            "_flow_meta": {
                "model": ns.selected_model,
                "orchestration_model": ns.selected_model,
                "final_response_model": ns.final_response_model_used,
                "stage_models": {
                    "planning": ns.selected_model,
                    "final_response": ns.final_response_model_used,
                },
                "ai_raw_response": ns.gpt_raw_content[:2000] if ns.gpt_raw_content else None,
                "ai_query_summary": ns.flow_ai_query_summary,
                "bot_sent_to_ai": ns.flow_bot_sent_to_ai_full,
                "customer_context_sent": ns.flow_customer_context_sent,
                "error": f"json_decode_error: {e}",
            },
        }
    except Exception as e:
        print(f"\n{'=' * 80}")
        print(f"❌ ERROR in get_bot_chat_response from GPT: {e}")
        print(f"   Error type: {type(e).__name__}")
        import traceback

        print("   Full traceback:")
        traceback.print_exc()
        print(f"{'=' * 80}\n")
        ns.generic_error_by_lang = {
            "ar": "عذراً، صار خطأ وأنا عم عالج طلبك حالياً. جرّب مرة ثانية أو تواصل معنا مباشرة.",
            "en": "Sorry, I encountered an issue understanding your request at the moment. Please try again or contact our staff directly.",
            "fr": "Désolé, j'ai rencontré un problème en traitant votre demande. Veuillez réessayer ou contacter notre équipe.",
            "franco": "عذراً، صار خطأ وأنا عم عالج طلبك حالياً. جرّب مرة ثانية أو تواصل معنا مباشرة.",
        }
        return {
            "action": "unknown_query",
            "bot_reply": ns.generic_error_by_lang.get(ns.current_preferred_lang, ns.generic_error_by_lang["en"]),
            "detected_language": ns.current_preferred_lang,
            "current_gender_from_config": ns.current_gender,  # Pass the actual gender from config
            "_flow_meta": {
                "model": ns.selected_model,
                "orchestration_model": ns.selected_model,
                "final_response_model": ns.final_response_model_used,
                "stage_models": {
                    "planning": ns.selected_model,
                    "final_response": ns.final_response_model_used,
                },
                "ai_raw_response": ns.gpt_raw_content[:2000] if ns.gpt_raw_content else None,
                "ai_query_summary": ns.flow_ai_query_summary,
                "bot_sent_to_ai": ns.flow_bot_sent_to_ai_full,
                "customer_context_sent": ns.flow_customer_context_sent,
                "error": f"{type(e).__name__}: {e}",
            },
        }
