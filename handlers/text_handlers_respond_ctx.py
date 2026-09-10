"""Bootstrap shared services for `_process_and_respond` phase pipeline."""

from __future__ import annotations

from typing import Any


def _lazy_bindings() -> dict[str, Any]:
    """Bindings actually read by phase 1 / phase 2."""
    from handlers.text_handlers_respond_intent import (
        _build_out_of_scope_reply,
        _is_out_of_clinic_scope_query,
    )
    from handlers.text_handlers_respond_reply import _handle_published_cm_runtime
    from services.conversation_router import get_gender_from_message, route
    from services.dynamic_messages_service import get_dynamic_message
    from services.interaction_flow_logger import is_flow_logging_enabled, log_interaction
    from services.language_detection_service import language_detection_service
    from services.user_persistence_service import user_persistence
    from utils.utils import (
        get_canonical_user_id_and_phone,
        get_firestore_db,
        save_conversation_message_to_firestore,
    )

    return {
        "_build_out_of_scope_reply": _build_out_of_scope_reply,
        "_handle_published_cm_runtime": _handle_published_cm_runtime,
        "_is_out_of_clinic_scope_query": _is_out_of_clinic_scope_query,
        "get_canonical_user_id_and_phone": get_canonical_user_id_and_phone,
        "get_dynamic_message": get_dynamic_message,
        "get_firestore_db": get_firestore_db,
        "get_gender_from_message": get_gender_from_message,
        "is_flow_logging_enabled": is_flow_logging_enabled,
        "language_detection_service": language_detection_service,
        "log_interaction": log_interaction,
        "router_route": route,
        "save_conversation_message_to_firestore": save_conversation_message_to_firestore,
        "user_persistence": user_persistence,
    }


def bootstrap_process_respond_ctx(ctx: dict[str, Any]) -> None:
    """Populate ctx with services required by phase 1+.

    Worker and inline Meta paths call `_process_and_respond` directly; they do not
    pass through `handle_message` imports. Idempotent per key.
    """
    for key, value in _lazy_bindings().items():
        if ctx.get(key) is None:
            ctx[key] = value


__all__ = ["bootstrap_process_respond_ctx"]
