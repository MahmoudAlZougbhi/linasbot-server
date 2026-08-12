"""LOC split: live_chat_service mixins under 500 lines; Qiscus adapter preserved."""

from __future__ import annotations

from pathlib import Path

from services.live_chat_service import LiveChatService, live_chat_service
from services.live_chat_service_operator import LiveChatOperatorMixin


def _line_count(rel: str) -> int:
    return len(Path(rel).read_text(encoding="utf-8").splitlines())


def test_live_chat_service_modules_under_500_lines() -> None:
    files = [Path("services/live_chat_service.py"), *sorted(Path("services").glob("live_chat_service_*.py"))]
    assert files
    for path in files:
        assert _line_count(str(path)) < 500, f"{path} is {_line_count(str(path))} lines"


def test_live_chat_service_preserves_public_api() -> None:
    assert isinstance(live_chat_service, LiveChatService)
    assert issubclass(LiveChatService, LiveChatOperatorMixin)
    for name in (
        "get_active_conversations",
        "get_metrics",
        "send_operator_message",
    ):
        assert callable(getattr(live_chat_service, name))


def test_live_chat_operator_keeps_qiscus_adapter() -> None:
    src = Path("services/live_chat_service_operator.py").read_text(encoding="utf-8")
    assert "Qiscus" in src
    assert "send_operator_message" in src
