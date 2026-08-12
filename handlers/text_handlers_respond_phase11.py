"""Core _process_and_respond phase 11."""

from __future__ import annotations

_PHASE_HALT = "_PHASE_HALT"


async def text_handlers_respond_phase11(ctx: dict):
    _dynamic_retrieval_flow_meta = ctx.get("_dynamic_retrieval_flow_meta")
    _flow_error_reason = ctx.get("_flow_error_reason")
    _prepend_multimodal_steps = ctx.get("_prepend_multimodal_steps")
    action = ctx.get("action")
    booking_retry = ctx.get("booking_retry")
    flow_meta = ctx.get("flow_meta")
    response_time_ms = ctx.get("response_time_ms")
    sent_reply = ctx.get("sent_reply")
    user_input_to_process = ctx.get("user_input_to_process")
    if _dynamic_retrieval_flow_meta:
        dr = _dynamic_retrieval_flow_meta
        bot_sent_selector = dr.get("bot_sent_to_selector", "")
        ai_selector_return = dr.get("selector_ai_raw_response", "")
        tool_round_trips = flow_meta.get("tool_round_trips") or []
        ai_first = flow_meta.get("ai_first_response")
        ai_error = flow_meta.get("error")
        ai_raw_or_error = flow_meta.get("ai_raw_response") or (f"AI error: {ai_error}" if ai_error else None)
        selected_titles = dr.get("selected_titles") or []
        loaded_content_full = dr.get("loaded_content_full") or ""
        loaded_content_block = (
            "Bot loaded from knowledge/price/style:\n  • " + "\n  • ".join(selected_titles)
            if selected_titles
            else f"Bot used default/general content. Action: {dr.get('action', 'normal')}."
        )
        if loaded_content_full:
            loaded_content_block += (
                f"\n\nFull loaded content sent to AI ({len(loaded_content_full)} chars):\n{loaded_content_full}"
            )
        ai_selected_str = (
            "AI selected from knowledge/price/style:\n  • " + "\n  • ".join(selected_titles) if selected_titles else ""
        )
        if ai_selector_return:
            ai_selected_str += f"\n\nRaw AI response:\n{ai_selector_return}"
        elif not ai_selected_str:
            ai_selected_str = (
                f"Files: {', '.join(dr.get('selected_files') or [])}, action: {dr.get('action', 'normal')}"
            )
        from services.dynamic_retrieval_service import (
            SELECTOR_MODEL,
            SELECTOR_MODEL_INPUT_PER_1M_USD,
            SELECTOR_MODEL_OUTPUT_PER_1M_USD,
        )

        sel_pt = dr.get("selector_prompt_tokens") or 0
        sel_ct = dr.get("selector_completion_tokens") or 0
        pt = flow_meta.get("prompt_tokens")
        ct = flow_meta.get("completion_tokens")
        stage_models = flow_meta.get("stage_models") or {}
        token_breakdown = flow_meta.get("token_breakdown") or {}
        first_call = token_breakdown.get("first_gpt_call") or token_breakdown.get("single_call") or {}
        second_call = token_breakdown.get("second_gpt_call") or {}
        orchestration_model = (
            flow_meta.get("orchestration_model") or stage_models.get("planning") or flow_meta.get("model") or "gpt-5.1"
        )
        final_model = flow_meta.get("final_response_model") or stage_models.get("final_response") or orchestration_model
        main_cost = flow_meta.get("cost_usd") or 0.0
        selector_cost = (sel_pt / 1_000_000 * SELECTOR_MODEL_INPUT_PER_1M_USD) + (
            sel_ct / 1_000_000 * SELECTOR_MODEL_OUTPUT_PER_1M_USD
        )
        steps = [
            {
                "step": 1,
                "title": "User → Bot",
                "content": user_input_to_process,
                "tokens": 0,
                "model": None,
                "cost_usd": None,
            },
            {
                "step": 2,
                "title": "Bot → AI (Selector)",
                "content": bot_sent_selector or "User message + file titles.",
                "tokens": sel_pt,
                "model": SELECTOR_MODEL,
                "cost_usd": round((sel_pt / 1_000_000 * SELECTOR_MODEL_INPUT_PER_1M_USD), 6) if sel_pt else None,
                "event_type": "selector_started",
            },
            {
                "step": 3,
                "title": "AI → Bot (Selector)",
                "content": ai_selected_str or "AI returned.",
                "tokens": sel_ct,
                "model": SELECTOR_MODEL,
                "cost_usd": round((sel_ct / 1_000_000 * SELECTOR_MODEL_OUTPUT_PER_1M_USD), 6) if sel_ct else None,
                "event_type": "selector_completed",
                "metadata": {"selected_files": selected_titles, "selected_count": len(selected_titles)},
            },
            {
                "step": 4,
                "title": "Bot loaded content",
                "content": loaded_content_block,
                "tokens": 0,
                "model": None,
                "cost_usd": None,
                "event_type": "retrieval_completed",
            },
        ]
        cust_ctx = flow_meta.get("customer_context_sent")
        if cust_ctx:
            steps.append(
                {
                    "step": 5,
                    "title": "Bot → AI (Customer context)",
                    "content": cust_ctx,
                    "tokens": 0,
                    "model": None,
                    "cost_usd": None,
                    "event_type": "customer_context_sent",
                }
            )
        steps.append(
            {
                "step": len(steps) + 1,
                "title": "Bot → AI (GPT planning)",
                "content": flow_meta.get("bot_sent_to_ai")
                or flow_meta.get("ai_query_summary")
                or "Merged content + user query sent to GPT.",
                "tokens": first_call.get("prompt_tokens", pt),
                "model": orchestration_model,
                "cost_usd": round(first_call.get("input_cost_usd") or flow_meta.get("input_cost_usd") or 0, 6)
                if (first_call.get("input_cost_usd") is not None or flow_meta.get("input_cost_usd") is not None)
                else None,
                "event_type": "main_ai_started",
            }
        )
        step_num = len(steps) + 1
        if tool_round_trips:
            steps.append(
                {
                    "step": step_num,
                    "title": "AI → Bot (requested tools)",
                    "content": ai_first or "AI requested tool calls.",
                    "tokens": 0,
                    "model": None,
                    "cost_usd": None,
                }
            )
            step_num += 1
            for tr in tool_round_trips:
                steps.append(
                    {
                        "step": step_num,
                        "title": f"AI requested: {tr.get('ai_requested', '?')}",
                        "content": f"Args: {tr.get('args', '{}')}",
                        "tokens": 0,
                        "model": None,
                        "cost_usd": None,
                    }
                )
                step_num += 1
                exec_step = {
                    "step": step_num,
                    "title": f"Bot → AI (executed {tr.get('ai_requested', '?')})",
                    "content": tr.get("bot_returned", ""),
                    "tokens": 0,
                    "model": None,
                    "cost_usd": None,
                }
                if tr.get("backend_execution"):
                    exec_step["metadata"] = {"backend_execution": tr["backend_execution"]}
                steps.append(exec_step)
                step_num += 1
            steps.append(
                {
                    "step": step_num,
                    "title": "AI → Bot (GPT final)",
                    "content": ai_raw_or_error or "(no content)",
                    "tokens": second_call.get("completion_tokens", ct),
                    "model": final_model,
                    "cost_usd": round(second_call.get("cost_usd") or flow_meta.get("output_cost_usd") or 0, 6)
                    if (second_call.get("cost_usd") is not None or flow_meta.get("output_cost_usd") is not None)
                    else None,
                    "event_type": "main_ai_completed",
                }
            )
            step_num += 1
        else:
            steps.append(
                {
                    "step": step_num,
                    "title": "AI → Bot (GPT)",
                    "content": ai_raw_or_error
                    or f"GPT returned. Model: {final_model} | Tokens: {(pt or 0) + (ct or 0)} | Time: {response_time_ms:.0f}ms",
                    "tokens": ct,
                    "model": final_model,
                    "cost_usd": round(main_cost, 6) if main_cost else None,
                    "event_type": "main_ai_completed",
                }
            )
            step_num += 1
        if flow_meta.get("error") or _flow_error_reason:
            err_msg = flow_meta.get("error") or _flow_error_reason or "Unknown error"
            err_step = {
                "step": step_num,
                "title": "❌ Error",
                "content": f"Step: AI → Bot (GPT) | {err_msg}",
                "tokens": 0,
                "model": None,
                "cost_usd": None,
                "event_type": "error",
            }
            if booking_retry:
                err_step["metadata"] = {"booking_retry": booking_retry}
            steps.append(err_step)
            step_num += 1
        resp_step = {
            "step": step_num,
            "title": "Bot → User",
            "content": sent_reply or "(no response)",
            "tokens": 0,
            "model": None,
            "cost_usd": None,
            "event_type": "response_sent",
        }
        if action in ("human_handover", "human_handover_confirmed"):
            resp_step["event_type"] = "handover_triggered"
            resp_step["metadata"] = {"handover": True}
        steps.append(resp_step)
        total_cost = selector_cost + main_cost
        summary_parts = [f"Selector ({SELECTOR_MODEL}): {sel_pt + sel_ct} tokens, ${selector_cost:.6f}"]
        if second_call:
            summary_parts.append(
                f"Planning GPT ({orchestration_model}): {(first_call.get('prompt_tokens', 0) or 0) + (first_call.get('completion_tokens', 0) or 0)} tokens, ${float(first_call.get('cost_usd') or 0):.6f}"
            )
            summary_parts.append(
                f"Final GPT ({final_model}): {(second_call.get('prompt_tokens', 0) or 0) + (second_call.get('completion_tokens', 0) or 0)} tokens, ${float(second_call.get('cost_usd') or 0):.6f}"
            )
        else:
            summary_parts.append(f"Main GPT ({final_model}): {(pt or 0) + (ct or 0)} tokens, ${main_cost:.6f}")
        summary_parts.append(f"Total cost: ${total_cost:.6f}")
        steps.append(
            {
                "step": step_num + 1,
                "title": "📊 Summary (usage & cost)",
                "content": " | ".join(summary_parts),
                "tokens": (sel_pt + sel_ct) + (pt or 0) + (ct or 0),
                "model": None,
                "cost_usd": round(total_cost, 6),
            }
        )
        flow_steps, msg_type = _prepend_multimodal_steps(steps, 1)
    else:
        tool_round_trips = flow_meta.get("tool_round_trips") or []
        ai_first = flow_meta.get("ai_first_response")
        ai_error = flow_meta.get("error")
        ai_raw_or_error = flow_meta.get("ai_raw_response") or (f"AI error: {ai_error}" if ai_error else None)
        pt = flow_meta.get("prompt_tokens")
        ct = flow_meta.get("completion_tokens")
        stage_models = flow_meta.get("stage_models") or {}
        token_breakdown = flow_meta.get("token_breakdown") or {}
        first_call = token_breakdown.get("first_gpt_call") or token_breakdown.get("single_call") or {}
        second_call = token_breakdown.get("second_gpt_call") or {}
        orchestration_model = (
            flow_meta.get("orchestration_model") or stage_models.get("planning") or flow_meta.get("model") or "gpt-5.1"
        )
        final_model = flow_meta.get("final_response_model") or stage_models.get("final_response") or orchestration_model
        main_cost = flow_meta.get("cost_usd") or 0.0
        steps = [
            {
                "step": 1,
                "title": "User → Bot",
                "content": user_input_to_process,
                "tokens": 0,
                "model": None,
                "cost_usd": None,
            },
        ]
        cust_ctx = flow_meta.get("customer_context_sent")
        if cust_ctx:
            steps.append(
                {
                    "step": 2,
                    "title": "Bot → AI (Customer context)",
                    "content": cust_ctx,
                    "tokens": 0,
                    "model": None,
                    "cost_usd": None,
                    "event_type": "customer_context_sent",
                }
            )
        steps.append(
            {
                "step": len(steps) + 1,
                "title": "Bot → AI",
                "content": flow_meta.get("bot_sent_to_ai")
                or flow_meta.get("ai_query_summary")
                or "Query + context sent to GPT.",
                "tokens": first_call.get("prompt_tokens", pt),
                "model": orchestration_model,
                "cost_usd": round(first_call.get("input_cost_usd") or flow_meta.get("input_cost_usd") or 0, 6)
                if (first_call.get("input_cost_usd") is not None or flow_meta.get("input_cost_usd") is not None)
                else None,
                "event_type": "main_ai_started",
            }
        )
        step_num = len(steps) + 1
        if tool_round_trips:
            steps.append(
                {
                    "step": step_num,
                    "title": "AI → Bot (requested tools)",
                    "content": ai_first or "AI requested tool calls.",
                    "tokens": 0,
                    "model": None,
                    "cost_usd": None,
                }
            )
            step_num += 1
            for _i, tr in enumerate(tool_round_trips):
                steps.append(
                    {
                        "step": step_num,
                        "title": f"AI requested: {tr.get('ai_requested', '?')}",
                        "content": f"Args: {tr.get('args', '{}')}",
                        "tokens": 0,
                        "model": None,
                        "cost_usd": None,
                    }
                )
                step_num += 1
                exec_step = {
                    "step": step_num,
                    "title": f"Bot → AI (executed {tr.get('ai_requested', '?')})",
                    "content": tr.get("bot_returned", ""),
                    "tokens": 0,
                    "model": None,
                    "cost_usd": None,
                }
                if tr.get("backend_execution"):
                    exec_step["metadata"] = {"backend_execution": tr["backend_execution"]}
                steps.append(exec_step)
                step_num += 1
            steps.append(
                {
                    "step": step_num,
                    "title": "AI → Bot (final response)",
                    "content": ai_raw_or_error or "(no content)",
                    "tokens": second_call.get("completion_tokens", ct),
                    "model": final_model,
                    "cost_usd": round(second_call.get("cost_usd") or flow_meta.get("output_cost_usd") or 0, 6)
                    if (second_call.get("cost_usd") is not None or flow_meta.get("output_cost_usd") is not None)
                    else None,
                    "event_type": "main_ai_completed",
                }
            )
            step_num += 1
        else:
            steps.append(
                {
                    "step": step_num,
                    "title": "AI → Bot",
                    "content": ai_raw_or_error
                    or f"GPT returned. Model: {final_model} | Tokens: {(pt or 0) + (ct or 0)} | Time: {response_time_ms:.0f}ms",
                    "tokens": ct,
                    "model": final_model,
                    "cost_usd": round(main_cost, 6) if main_cost else None,
                    "event_type": "main_ai_completed",
                }
            )
            step_num += 1
        if flow_meta.get("error") or _flow_error_reason:
            err_msg = flow_meta.get("error") or _flow_error_reason or "Unknown error"
            err_step = {
                "step": step_num,
                "title": "❌ Error",
                "content": f"Step: AI → Bot | {err_msg}",
                "tokens": 0,
                "model": None,
                "cost_usd": None,
                "event_type": "error",
            }
            if booking_retry:
                err_step["metadata"] = {"booking_retry": booking_retry}
            steps.append(err_step)
            step_num += 1
        resp_step = {
            "step": step_num,
            "title": "Bot → User",
            "content": sent_reply or "(no response)",
            "tokens": 0,
            "model": None,
            "cost_usd": None,
            "event_type": "response_sent",
        }
        if action in ("human_handover", "human_handover_confirmed"):
            resp_step["event_type"] = "handover_triggered"
            resp_step["metadata"] = {"handover": True}
        steps.append(resp_step)
        if second_call:
            summary_parts = [
                f"Planning GPT ({orchestration_model}): {(first_call.get('prompt_tokens', 0) or 0) + (first_call.get('completion_tokens', 0) or 0)} tokens, ${float(first_call.get('cost_usd') or 0):.6f}",
                f"Final GPT ({final_model}): {(second_call.get('prompt_tokens', 0) or 0) + (second_call.get('completion_tokens', 0) or 0)} tokens, ${float(second_call.get('cost_usd') or 0):.6f}",
                f"Total cost: ${main_cost:.6f}",
            ]
        else:
            summary_parts = [
                f"GPT ({final_model}): {(pt or 0) + (ct or 0)} tokens, ${main_cost:.6f}",
                f"Total cost: ${main_cost:.6f}",
            ]
        steps.append(
            {
                "step": step_num + 1,
                "title": "📊 Summary (usage & cost)",
                "content": " | ".join(summary_parts),
                "tokens": (pt or 0) + (ct or 0),
                "model": None,
                "cost_usd": round(main_cost, 6),
            }
        )
        flow_steps, msg_type = _prepend_multimodal_steps(steps, 1)
    _pack = [
        "SELECTOR_MODEL",
        "SELECTOR_MODEL_INPUT_PER_1M_USD",
        "SELECTOR_MODEL_OUTPUT_PER_1M_USD",
        "_dynamic_retrieval_flow_meta",
        "_flow_error_reason",
        "_i",
        "_prepend_multimodal_steps",
        "action",
        "ai_error",
        "ai_first",
        "ai_raw_or_error",
        "ai_selected_str",
        "ai_selector_return",
        "booking_retry",
        "bot_sent_selector",
        "ct",
        "cust_ctx",
        "dr",
        "err_msg",
        "err_step",
        "exec_step",
        "final_model",
        "first_call",
        "flow_meta",
        "flow_steps",
        "loaded_content_block",
        "loaded_content_full",
        "main_cost",
        "msg_type",
        "orchestration_model",
        "pt",
        "resp_step",
        "response_time_ms",
        "second_call",
        "sel_ct",
        "sel_pt",
        "selected_titles",
        "selector_cost",
        "sent_reply",
        "stage_models",
        "step_num",
        "steps",
        "summary_parts",
        "token_breakdown",
        "tool_round_trips",
        "total_cost",
        "tr",
        "user_input_to_process",
    ]
    for _k in _pack:
        if _k in locals():
            ctx[_k] = locals()[_k]
    return None
