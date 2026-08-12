"""LOC split: chat_response_service helpers/runtime under 500 lines; public exports preserved."""

from __future__ import annotations

from pathlib import Path

from services.chat_response_service import (
    _extract_customer_appointments_list,
    _is_placeholder_booking_customer_name,
    get_bot_chat_response,
)


def _line_count(rel: str) -> int:
    return len(Path(rel).read_text(encoding="utf-8").splitlines())


def test_chat_response_service_modules_under_500_lines() -> None:
    files = [
        *sorted(Path("services").glob("chat_response_service*.py")),
        *sorted(Path("services").glob("chat_response_runtime*.py")),
    ]
    assert files
    for path in files:
        assert _line_count(str(path)) < 500, f"{path} is {_line_count(str(path))} lines"


def test_chat_response_service_preserves_public_api() -> None:
    assert callable(get_bot_chat_response)
    assert callable(_extract_customer_appointments_list)
    assert callable(_is_placeholder_booking_customer_name)
    assert _extract_customer_appointments_list({}) == []
    assert _is_placeholder_booking_customer_name("client") is True
    assert _is_placeholder_booking_customer_name("Maha") is False
