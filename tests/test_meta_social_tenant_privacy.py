"""Tenant social identities and provider errors must stay out of application logs."""

from __future__ import annotations

from typing import Any

import pytest

import config
from services import social_messaging_processor
from services.meta_messaging import MetaMessagingSettings


@pytest.mark.asyncio
async def test_state_restore_failure_log_omits_sender_and_exception_text(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sender_marker = "998877665544332211"
    error_marker = "private-provider-error-body"
    user_id = f"tenant-a:facebook:{sender_marker}"

    async def restore(_user_id: str) -> dict[str, Any]:
        raise RuntimeError(error_marker)

    async def handle(**_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(social_messaging_processor, "get_user_state_from_firestore", restore)
    monkeypatch.setattr(social_messaging_processor, "handle_message", handle)
    settings = MetaMessagingSettings(
        enabled=True,
        app_secret="not-used-in-simulation",
        page_id="445566778899",
        page_access_token="not-used-in-simulation",
        instagram_account_id="",
        verify_token="not-used-in-simulation",
        graph_api_version="v24.0",
        app_id="998877",
        app_key="saas_tech_provider",
        tenant_id="tenant-a",
        binding_id="binding-a",
    )

    try:
        await social_messaging_processor.process_meta_social_event(
            {
                "channel": "facebook",
                "sender_id": sender_marker,
                "recipient_id": settings.page_id,
                "account_id": settings.page_id,
                "message_id": "mid-private-log-test",
                "text": "hello",
                "tenant_id": "tenant-a",
            },
            settings,
            simulation=True,
        )
    finally:
        for mapping in (
            config.user_data_whatsapp,
            config.user_names,
            config.user_gender,
        ):
            mapping.pop(user_id, None)

    captured = capsys.readouterr()
    rendered = captured.out + captured.err
    assert "state_restore_skipped type=RuntimeError" in rendered
    assert sender_marker not in rendered
    assert error_marker not in rendered
