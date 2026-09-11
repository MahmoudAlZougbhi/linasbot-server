"""Shared fixtures and helpers for Meta social image quota delivery tests."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterator
from typing import Any

import pytest

import config
from services import social_messaging_processor as processor
from services.meta_messaging import MetaMessagingSettings
from tests.meta_compliance_helpers import _FakeFirestore


class _Adapter:
    def __init__(self, responses: list[dict[str, Any] | BaseException]) -> None:
        self.responses = responses
        self.messages: list[str] = []

    async def send_text_message(self, _sender_id: str, message: str) -> dict[str, Any]:
        self.messages.append(message)
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response

    async def send_typing(self, _sender_id: str) -> dict[str, Any]:
        return {"success": True}

    async def fetch_participant_profile(self, _sender_id: str) -> dict[str, Any]:
        return {}

    async def close(self) -> None:
        return None


def _accepted(message_id: str) -> dict[str, Any]:
    return {"success": True, "provider": "meta", "message_id": message_id}


def _settings() -> MetaMessagingSettings:
    return MetaMessagingSettings(
        enabled=True,
        app_secret="unused",
        page_id="page-id",
        page_access_token="token",
        instagram_account_id="",
        verify_token="unused",
        graph_api_version="v24.0",
        app_id="app-id",
        app_key="app-key",
        tenant_id="tenant-a",
        binding_id="binding-a",
    )


def _event() -> dict[str, Any]:
    return {
        "channel": "facebook",
        "sender_id": "sender-a",
        "sender_name": "Customer",
        "recipient_id": "page-id",
        "account_id": "page-id",
        "message_id": "provider-inbound-a",
        "tenant_id": "tenant-a",
        "text": "Please inspect these",
        "attachments": [
            {"type": "image", "id": "image-1"},
            {"type": "file", "id": "file-1"},
            {"type": "image", "id": "image-2"},
            {"type": "audio", "id": "audio-1"},
            {"type": "image", "id": "image-3"},
        ],
    }


def _text_event() -> dict[str, Any]:
    event = _event()
    event["attachments"] = []
    return event


@pytest.fixture()
def runtime(monkeypatch: pytest.MonkeyPatch) -> Iterator[_FakeFirestore]:
    import services.ai_limits_enforcement as limits
    import utils.utils

    db = _FakeFirestore()
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setattr(utils.utils, "get_firestore_db", lambda: db)

    async def restore(_user_id: str) -> dict[str, Any]:
        return {}

    async def persist_name(_user_id: str, _name: str) -> None:
        return None

    monkeypatch.setattr(processor, "get_user_state_from_firestore", restore)
    monkeypatch.setattr("services.social_customer_name.save_user_name_to_firestore", persist_name)
    quota_calls: list[bool] = []

    def enforce(**kwargs: Any) -> Any:
        from services.ai_usage_limits import QuotaDecision

        quota_calls.append(bool(kwargs["consume"]))
        if getattr(db, "quota_mode", "truncated") == "allowed":
            return QuotaDecision(
                allowed=True,
                allowed_amount=int(kwargs["amount"]),
                reason="ok",
            )
        return QuotaDecision(
            allowed=True,
            allowed_amount=2,
            customer_message="quota notice",
            reason="image_truncated",
        )

    db.quota_calls = quota_calls  # type: ignore[attr-defined]
    db.quota_mode = "truncated"  # type: ignore[attr-defined]
    monkeypatch.setattr(
        limits,
        "enforce_image_analysis_quota",
        enforce,
    )
    snapshots = {
        "user_data_whatsapp": dict(config.user_data_whatsapp),
        "user_names": dict(config.user_names),
        "user_gender": dict(config.user_gender),
    }
    yield db
    for name, snapshot in snapshots.items():
        mapping = getattr(config, name)
        mapping.clear()
        mapping.update(snapshot)


def _install_adapter(monkeypatch: pytest.MonkeyPatch, adapter: _Adapter) -> None:
    monkeypatch.setattr(processor, "MetaMessagingAdapter", lambda **_kwargs: adapter)


def _install_handler(
    monkeypatch: pytest.MonkeyPatch,
    callback: Callable[[dict[str, Any]], Awaitable[None]],
) -> None:
    async def handle(**kwargs: Any) -> None:
        await callback(kwargs)

    monkeypatch.setattr(processor, "handle_message", handle)


async def _send_primary(kwargs: dict[str, Any]) -> None:
    await kwargs["send_message_func"](kwargs["user_id"], "primary reply")


def processor_meta_document(
    db: _FakeFirestore,
    event_id: str,
    purpose: str,
) -> dict[str, Any]:
    from services.meta_outbound_attempts import _attempt_document_id

    return (
        db.collection("artifacts")
        .document("linas-ai-bot-backend")
        .collection("meta_outbound_attempts")
        .document(_attempt_document_id(event_id, purpose))
        .data
    )
