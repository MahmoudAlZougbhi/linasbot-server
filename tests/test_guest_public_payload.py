"""Guest session payload stays readable when projection or message shape is odd."""

from types import SimpleNamespace

from modules.guest_ai_api import _public_messages, _session_payload


def test_public_messages_coerce_roles_and_timestamps() -> None:
    rows = _public_messages(
        [
            {"id": "1", "role": "ai", "content": "hello", "created_at": "not-a-time"},
            {"id": "2", "role": "user", "content": "hi", "created_at": 12},
        ]
    )
    assert rows[0]["role"] == "assistant"
    assert rows[0]["created_at"] == 0.0
    assert rows[1]["created_at"] == 12.0


def test_session_payload_survives_projection_failure(monkeypatch) -> None:
    def _boom(*_args, **_kwargs):
        raise RuntimeError("projection down")

    monkeypatch.setattr("services.guest.guest_inbox_bridge.publish_guest_view", _boom)
    session = SimpleNamespace(
        id="guest-session-1",
        questions_used=0,
        messages=[SimpleNamespace(id="m1", role="assistant", content="Hi", created_at=1.5)],
    )
    payload = _session_payload(session, None)
    assert payload["messages"][0]["content"] == "Hi"
    assert payload["messages"][0]["role"] == "assistant"
    assert payload["live_token"] == ""
