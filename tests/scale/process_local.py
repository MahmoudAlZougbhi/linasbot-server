"""Helpers to wipe process-local conversation maps between simulated nodes."""

from __future__ import annotations

import config


def wipe_process_conversation_state() -> None:
    config.user_data_whatsapp.clear()
    config.user_names.clear()
    config.user_gender.clear()
    config.user_greeting_stage.clear()
    config.gender_attempts.clear()
    config.user_in_human_takeover_mode.clear()
    config.user_booking_state.clear()
    config.user_pending_messages.clear()
    config.user_photo_analysis_count.clear()
    config.user_in_training_mode.clear()
    config.user_context.clear()
