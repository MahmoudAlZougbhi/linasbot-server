"""Bootstrap shared services for `_process_and_respond` phase pipeline."""

from __future__ import annotations

from typing import Any


def bootstrap_process_respond_ctx(ctx: dict[str, Any]) -> None:
    """Populate ctx with firestore/language services required by phase 1+.

    Worker and inline Meta paths call `_process_and_respond` directly; they do not
    pass through `handle_message` imports. Idempotent per turn.
    """
    if ctx.get("language_detection_service") is not None:
        return
    from services.dynamic_messages_service import get_dynamic_message
    from services.interaction_flow_logger import is_flow_logging_enabled, log_interaction
    from services.language_detection_service import language_detection_service
    from services.user_persistence_service import user_persistence
    from utils.utils import (
        get_canonical_user_id_and_phone,
        get_firestore_db,
        save_conversation_message_to_firestore,
    )

    ctx.update(
        {
            "get_canonical_user_id_and_phone": get_canonical_user_id_and_phone,
            "get_dynamic_message": get_dynamic_message,
            "get_firestore_db": get_firestore_db,
            "is_flow_logging_enabled": is_flow_logging_enabled,
            "language_detection_service": language_detection_service,
            "log_interaction": log_interaction,
            "save_conversation_message_to_firestore": save_conversation_message_to_firestore,
            "user_persistence": user_persistence,
        }
    )


__all__ = ["bootstrap_process_respond_ctx"]
