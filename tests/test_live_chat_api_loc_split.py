"""LOC split: live_chat_api re-exports helpers/debug under 500 lines."""

from __future__ import annotations

from pathlib import Path


def _line_count(rel: str) -> int:
    return len(Path(rel).read_text(encoding="utf-8").splitlines())


def test_live_chat_api_modules_under_500_lines() -> None:
    assert _line_count("modules/live_chat_api.py") < 500
    assert _line_count("modules/live_chat_api_helpers.py") < 500
    assert _line_count("modules/live_chat_api_debug.py") < 500


def test_live_chat_api_preserves_broadcast_sse_export() -> None:
    from modules import live_chat_api
    from modules.live_chat_api_helpers import broadcast_sse_event as helper_broadcast

    assert live_chat_api.broadcast_sse_event is helper_broadcast
    assert callable(live_chat_api.broadcast_sse_event)
    assert callable(live_chat_api.get_unified_chats)
    # Debug routes registered via side-effect import.
    assert hasattr(live_chat_api, "live_chat_api_debug")
