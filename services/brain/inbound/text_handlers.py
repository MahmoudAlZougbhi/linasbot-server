"""Inbound text handler package. VERSION museum removed."""

from __future__ import annotations

from services.brain.inbound.text_handlers_delayed import _delayed_process_messages
from services.brain.inbound.text_handlers_firestore import _delayed_processing_tasks
from services.brain.inbound.text_handlers_message import handle_message
from services.brain.inbound.text_handlers_respond import _process_and_respond

__all__ = [
    "handle_message",
    "_delayed_process_messages",
    "_process_and_respond",
    "_delayed_processing_tasks",
]
