"""Core _process_and_respond phase 10."""
from __future__ import annotations

import time
from typing import Any

_PHASE_HALT = "_PHASE_HALT"


async def text_handlers_respond_phase10(ctx: dict):
    _looks_like_booking_offer_confirmation_question = ctx.get('_looks_like_booking_offer_confirmation_question')
    action = ctx.get('action')
    booking_origin_query = ctx.get('booking_origin_query')
    sent_reply = ctx.get('sent_reply')
    start_time = ctx.get('start_time')
    step_start = ctx.get('step_start')
    steps_list = ctx.get('steps_list')
    user_data = ctx.get('user_data')
    user_image_base64 = ctx.get('user_image_base64')
    user_image_format = ctx.get('user_image_format')
    user_input_to_process = ctx.get('user_input_to_process')
    voice_meta = ctx.get('voice_meta')
    if _looks_like_booking_offer_confirmation_question(sent_reply):
        booking_origin_query = (
            user_data.get("original_question") or user_data.get("pending_clarification_query") or user_input_to_process
        )
        user_data["awaiting_booking_offer_confirmation"] = True
        user_data["booking_offer_origin_query"] = booking_origin_query
        user_data["last_bot_question_type"] = "booking_offer_confirmation"
    else:
        user_data["awaiting_booking_offer_confirmation"] = False
        user_data["booking_offer_origin_query"] = None
        if user_data.get("last_bot_question_type") == "booking_offer_confirmation":
            user_data["last_bot_question_type"] = None

    # Flow logging for dashboard transparency
    response_time_ms = (time.time() - start_time) * 1000
    flow_source = (
        "rate_limit" if action == "rate_limit_exceeded" else "moderation" if action == "content_moderated" else "gpt"
    )
    flow_steps = None
    msg_type = "text"

    # Build multimodal prepended steps for Activity Flow
    def _prepend_multimodal_steps(steps_list: Any, step_start: int) -> tuple:
        prepended = []
        offset = 0
        voice_meta = user_data.pop("_voice_flow_meta", None)
        if voice_meta:
            prepended.extend(
                [
                    {
                        "step": step_start,
                        "title": "Voice received",
                        "content": "User sent voice message.",
                        "event_type": "voice_received",
                        "status": "success",
                        "message_type": "voice",
                    },
                    {
                        "step": step_start + 1,
                        "title": "Voice downloaded/prepared",
                        "content": f"Audio converted to MP3. Duration: {voice_meta.get('audio_duration_seconds', 0):.2f}s.",
                        "event_type": "voice_downloaded",
                        "status": "success",
                        "message_type": "voice",
                    },
                    {
                        "step": step_start + 2,
                        "title": "Transcription started",
                        "content": f"Sent to {voice_meta.get('transcription_model', 'gpt-4o-transcribe')}.",
                        "event_type": "transcription_started",
                        "model": voice_meta.get("transcription_model"),
                        "message_type": "voice",
                    },
                    {
                        "step": step_start + 3,
                        "title": "Transcription completed",
                        "content": f"Result: {voice_meta.get('transcription_length', 0)} chars in {voice_meta.get('transcription_duration_ms', 0):.0f}ms.",
                        "event_type": "transcription_completed",
                        "status": voice_meta.get("status", "success"),
                        "duration_ms": voice_meta.get("transcription_duration_ms"),
                        "message_type": "voice",
                    },
                ]
            )
            offset = 4
        if user_image_base64:
            prepended.extend(
                [
                    {
                        "step": step_start + offset,
                        "title": "Image received",
                        "content": "User sent image.",
                        "event_type": "image_received",
                        "status": "success",
                        "message_type": "image",
                    },
                    {
                        "step": step_start + offset + 1,
                        "title": "Image prepared",
                        "content": f"Extracted base64, format: {user_image_format}.",
                        "event_type": "image_prepared",
                        "status": "success",
                        "metadata": {"image_format": user_image_format},
                        "message_type": "image",
                    },
                ]
            )
            offset += 2
        for s in steps_list:
            s["step"] = s["step"] + offset
        return prepended + steps_list, "voice" if voice_meta else ("image" if user_image_base64 else "text")
    _pack = ['_looks_like_booking_offer_confirmation_question', 'action', 'booking_origin_query', 'flow_source', 'flow_steps', 'msg_type', 'offset', 'prepended', 'response_time_ms', 's', 'sent_reply', 'start_time', 'step_start', 'steps_list', 'user_data', 'user_image_base64', 'user_image_format', 'user_input_to_process', 'voice_meta']
    for _k in _pack:
        if _k in locals():
            ctx[_k] = locals()[_k]
    return None
