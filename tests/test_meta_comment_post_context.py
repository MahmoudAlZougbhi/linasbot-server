"""Comment webhooks must bind AI to the post, never the parent comment."""

from __future__ import annotations

import httpx
import pytest

from services.meta_comment_events import parse_meta_comment_events
from services.meta_comment_post_context import enrich_comment_event_post
from services.meta_comment_post_ids import (
    comment_post_ids_match,
    facebook_post_id_from_compound,
    facebook_post_id_from_feed_value,
)
from tests.test_meta_comment_replies import _binding, _facebook_comment_payload, _instagram_comment_payload


def test_nested_facebook_parent_comment_is_not_the_post() -> None:
    payload = _facebook_comment_payload()
    value = payload["entry"][0]["changes"][0]["value"]
    del value["post_id"]
    value["parent_id"] = "111_222_333"
    value["comment_id"] = "111_222_333"
    events = parse_meta_comment_events(payload, channel="facebook", page_id="111")
    assert len(events) == 1
    assert events[0]["post_id"] == "111_222"
    assert events[0]["parent_id"] == "111_222_333"
    assert events[0]["post_id"] != events[0]["parent_id"]


def test_facebook_photo_id_is_the_post_when_post_id_missing() -> None:
    value = {
        "parent_id": "111_222_333",
        "photo_id": "111_999",
        "comment_id": "c2",
    }
    assert facebook_post_id_from_feed_value(value) == "111_999"


def test_compound_comment_id_collapses_to_page_post() -> None:
    assert facebook_post_id_from_compound("111_222_333") == "111_222"
    assert facebook_post_id_from_compound("111_222") == "111_222"
    assert facebook_post_id_from_compound("opaque-comment") == ""


def test_cm_post_rules_match_facebook_page_post_aliases() -> None:
    assert comment_post_ids_match("111_222", "222")
    assert comment_post_ids_match("111_222_333", "111_222")
    assert not comment_post_ids_match("111_222", "111_999")


def test_instagram_reply_without_media_leaves_post_empty_for_graph() -> None:
    payload = _instagram_comment_payload()
    value = payload["entry"][0]["changes"][0]["value"]
    del value["media"]
    value["parent_id"] = "igc1"
    value["id"] = "igc2"
    events = parse_meta_comment_events(payload, channel="instagram", instagram_account_id="222")
    assert len(events) == 1
    assert events[0]["post_id"] == ""
    assert events[0]["parent_id"] == "igc1"


@pytest.mark.asyncio
async def test_enrich_loads_instagram_media_and_caption() -> None:
    binding = _binding(channel="instagram", asset_id="222", instagram_id="222")

    async def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/igc2"):
            return httpx.Response(
                200,
                json={
                    "id": "igc2",
                    "text": "price?",
                    "media": {"id": "media-laser", "caption": "Full body laser 9 sessions"},
                    "parent_id": "igc1",
                },
            )
        raise AssertionError(path)

    event = {
        "channel": "instagram",
        "comment_id": "igc2",
        "post_id": "",
        "media_id": "",
        "parent_id": "igc1",
        "text": "price?",
    }
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        out = await enrich_comment_event_post(
            event,
            binding=binding,
            token="token",
            graph_api_version="v24.0",
            client=client,
        )
    assert out["post_id"] == "media-laser"
    assert out["caption"] == "Full body laser 9 sessions"


@pytest.mark.asyncio
async def test_enrich_loads_facebook_post_not_parent_comment() -> None:
    binding = _binding()

    async def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/c2"):
            return httpx.Response(
                200,
                json={
                    "id": "c2",
                    "message": "and the price?",
                    "post": {"id": "111_555", "message": "Spring facial offer"},
                    "parent": {"id": "c1", "message": "How much?"},
                },
            )
        if path.endswith("/111_555"):
            return httpx.Response(200, json={"id": "111_555", "message": "Spring facial offer"})
        raise AssertionError(path)

    event = {
        "channel": "facebook",
        "comment_id": "c2",
        "post_id": "",
        "parent_id": "c1",
        "text": "and the price?",
    }
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        out = await enrich_comment_event_post(
            event,
            binding=binding,
            token="token",
            graph_api_version="v24.0",
            client=client,
        )
    assert out["post_id"] == "111_555"
    assert out["caption"] == "Spring facial offer"
    assert out["parent_comment"] == "How much?"
    assert out["parent_id"] == "c1"


@pytest.mark.asyncio
async def test_processor_sends_nested_facebook_post_id_to_brain(monkeypatch) -> None:
    from unittest import mock

    from services.meta_comment_events import ResolvedMetaCommentEvent
    from services.meta_comment_replies import process_meta_comment_event
    from tests.test_meta_comment_replies import _settings
    from tests.test_meta_comment_replies_more import MetaCommentProcessorTests

    helper = MetaCommentProcessorTests()
    helper.setUp()
    try:
        binding = helper._verified_binding()
        from services.meta_comment_reply_settings import set_comment_reply_setting

        set_comment_reply_setting(
            tenant_id=binding.tenant_id,
            app_key=binding.app_key,
            channel=binding.channel,
            asset_id=binding.asset_id,
            enabled=True,
        )
        payload = _facebook_comment_payload()
        value = payload["entry"][0]["changes"][0]["value"]
        del value["post_id"]
        value["parent_id"] = "111_222_333"
        event = parse_meta_comment_events(payload, channel="facebook", page_id="111")[0]
        generate = mock.AsyncMock(return_value="ok")
        monkeypatch.setattr("services.meta_comment_replies._generate_comment_reply_text", generate)
        monkeypatch.setattr(
            "services.meta_comment_replies._comment_has_page_reply",
            mock.AsyncMock(return_value=False),
        )
        result = await process_meta_comment_event(
            ResolvedMetaCommentEvent(event=event, settings=_settings(binding), binding=binding),
            simulation=True,
        )
        assert result.status == "simulated"
        ctx = generate.await_args.kwargs["comment_context"]
        assert ctx["post_id"] == "111_222"
        assert ctx["post_id"] != ctx["parent_id"]
    finally:
        helper.tearDown()
