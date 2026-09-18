"""LOC split: text_handlers_message greeting/takeover under 500 lines; public exports preserved."""

from __future__ import annotations

from pathlib import Path

from services.brain.greeting_detect import GREETING_INACTIVITY_SECONDS
from services.brain.inbound.text_handlers_message import handle_message
from services.brain.inbound.text_handlers_message_takeover import (
    maybe_send_takeover_autoreply,
    resolve_conversation_doc_ref,
    trigger_human_takeover,
)


def _line_count(rel: str) -> int:
    return len(Path(rel).read_text(encoding="utf-8").splitlines())


def test_text_handlers_message_modules_under_500_lines() -> None:
    assert _line_count("services/brain/inbound/text_handlers_message.py") < 500
    assert _line_count("services/brain/greeting_detect.py") < 500
    assert _line_count("services/brain/inbound/text_handlers_message_takeover.py") < 500


def test_text_handlers_message_preserves_public_api() -> None:
    parent_src = Path("services/brain/inbound/text_handlers.py").read_text(encoding="utf-8")
    assert "from services.brain.inbound.text_handlers_message import handle_message" in parent_src
    assert callable(handle_message)
    assert GREETING_INACTIVITY_SECONDS == 43200
    assert callable(maybe_send_takeover_autoreply)
    assert callable(resolve_conversation_doc_ref)
    assert callable(trigger_human_takeover)
