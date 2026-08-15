"""Private comment replies require an authenticated provider message identifier."""

from __future__ import annotations

import httpx
import pytest

from services.meta_app_registry import APP_A_KEY, MetaAssetBinding
from services.meta_comment_private_reply import send_comment_private_reply


def _binding(channel: str) -> MetaAssetBinding:
    return MetaAssetBinding(
        binding_id=f"binding-{channel}",
        tenant_id="linas",
        channel=channel,  # type: ignore[arg-type]
        asset_id="17841413184256533" if channel == "instagram" else "378696005334409",
        page_id="378696005334409" if channel == "facebook" else "",
        instagram_account_id="17841413184256533" if channel == "instagram" else "",
        app_key=APP_A_KEY,
        credential_id="credential",
        status="active",
        generation=1,
        created_at=1.0,
        updated_at=1.0,
        auth_flow="instagram_login" if channel == "instagram" else "facebook_login",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("channel", ["facebook", "instagram"])
async def test_private_reply_rejects_2xx_without_message_id(channel: str) -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"success": True})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        ok, reason, _body = await send_comment_private_reply(
            client,
            binding=_binding(channel),
            comment_id="comment-1",
            message="hello",
            token="token",
            graph_api_version="v24.0",
        )
    assert ok is False
    assert reason == "missing_reply_id"


@pytest.mark.asyncio
async def test_private_reply_rejects_2xx_error_payload() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"error": {"code": 10, "error_subcode": 2018336, "message": "sensitive request detail"}},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        ok, reason, body = await send_comment_private_reply(
            client,
            binding=_binding("instagram"),
            comment_id="comment-1",
            message="hello",
            token="token",
            graph_api_version="v24.0",
        )
    assert ok is False
    assert reason == "graph_http_200_code_10_subcode_2018336"
    assert body == {"error": {"code": 10, "error_subcode": 2018336}}
    assert "sensitive request detail" not in str(body)


@pytest.mark.asyncio
async def test_instagram_private_reply_accepts_message_id() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"recipient_id": "igsid", "message_id": "message-1"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        ok, reason, body = await send_comment_private_reply(
            client,
            binding=_binding("instagram"),
            comment_id="comment-1",
            message="hello",
            token="token",
            graph_api_version="v24.0",
        )
    assert ok is True
    assert reason == "sent"
    assert body["message_id"] == "message-1"
