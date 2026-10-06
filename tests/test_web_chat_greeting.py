"""Web chat greeting comes from the owner or stays absent."""

from services.integrations.web_chat.processor import default_greeting


def test_default_greeting_is_empty_without_owner_text() -> None:
    assert default_greeting("en") == ""
    assert default_greeting("ar") == ""
    assert "How can I help you today" not in default_greeting("en")
