"""WhatsApp image/voice reach Brain as inbound media, not a parallel vision stack."""

from __future__ import annotations

from inspect import getsource

import pytest

from services.customer_reply_v2.inbound_media import (
    inbound_payload_from_user_data,
    mark_inbound_attachment,
    store_inbound_image,
)


def test_inbound_from_attachment_type() -> None:
    from services.customer_reply_v2.inbound_media import inbound_from_attachment_type

    assert inbound_from_attachment_type("image") == {"attachment_types": ["image"]}
    assert inbound_from_attachment_type("audio", transcript="hi") == {
        "attachment_types": ["audio"],
        "transcript": "hi",
    }
    assert inbound_from_attachment_type("text") == {}
    assert inbound_from_attachment_type("video") == {"attachment_types": ["video"]}
    assert inbound_from_attachment_type("document", extract="hours.pdf") == {
        "attachment_types": ["file"],
        "extract": "hours.pdf",
    }
    from services.customer_reply_v2.inbound_media import planner_text_from_inbound

    assert planner_text_from_inbound({"transcript": "hello"}, text="") == "hello"
    assert planner_text_from_inbound({"extract": "hours.pdf"}, text="caption") == "caption"


def test_mark_image_and_voice_inbound() -> None:
    photo: dict = {}
    mark_inbound_attachment(photo, "image")
    view = inbound_payload_from_user_data(photo)
    assert view["attachment_types"] == ["image"]
    assert not view.get("image_media_id")

    voice: dict = {}
    mark_inbound_attachment(voice, "audio", transcript="hello from voice")
    audio = inbound_payload_from_user_data(voice)
    assert audio["attachment_types"] == ["audio"]
    assert audio["transcript"] == "hello from voice"


def test_phase2_image_flag_without_storing_bytes() -> None:
    view = inbound_payload_from_user_data({}, has_image=True)
    assert view["attachment_types"] == ["image"]
    assert "image_media_id" not in view or not view.get("image_media_id")


@pytest.mark.asyncio
async def test_cloud_image_hydrate_stores_resource_id(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LINASBOT_DATA_ROOT", str(tmp_path / "data"))
    from services.whatsapp_cloud.inbound_media_cloud import hydrate_cloud_inbound_snapshot

    async def fake_download(*, access_token: str, media_id: str, max_bytes: int = 8_000_000):
        _ = access_token, media_id, max_bytes
        return b"\xff\xd8\xff\xd9 inbound", "image/jpeg"

    monkeypatch.setattr("services.whatsapp_cloud.inbound_media_cloud._load_token", lambda _s: "tok")
    monkeypatch.setattr(
        "services.whatsapp_cloud.graph_client.download_media_bytes",
        fake_download,
    )
    snapshot = await hydrate_cloud_inbound_snapshot(
        {"tenant_id": "cloud-shop", "message_type": "image", "media_id": "12345"}
    )
    assert snapshot["image_media_id"].startswith("prdim_")


@pytest.mark.asyncio
async def test_cloud_audio_hydrate_keeps_transcript(monkeypatch) -> None:
    from services.whatsapp_cloud.inbound_media_cloud import hydrate_cloud_inbound_snapshot

    async def fake_download(*, access_token: str, media_id: str, max_bytes: int = 8_000_000):
        _ = access_token, media_id, max_bytes
        return b"OggSxxxx", "audio/ogg"

    async def fake_stt(*, data: bytes, filename: str = "") -> dict:
        _ = data, filename
        return {"ok": True, "text": "I want a facial", "model": "whisper-1"}

    monkeypatch.setattr("services.whatsapp_cloud.inbound_media_cloud._load_token", lambda _s: "tok")
    monkeypatch.setattr(
        "services.whatsapp_cloud.graph_client.download_media_bytes",
        fake_download,
    )
    monkeypatch.setattr(
        "services.customer_reply_v2.inbound_stt.transcribe_inbound_audio",
        fake_stt,
    )
    snapshot = await hydrate_cloud_inbound_snapshot(
        {
            "tenant_id": "cloud-stt-shop",
            "message_type": "audio",
            "media_id": "67890",
            "provider_message_id": "wamid.1",
        }
    )
    assert snapshot["transcript"] == "I want a facial"
    from services.membership.expense_journal import list_events

    events = list_events(tenant_id="cloud-stt-shop", category="stt")
    assert events
    assert events[0].amount_usd is None


@pytest.mark.asyncio
async def test_cloud_document_hydrate_extracts_text(monkeypatch) -> None:
    from services.whatsapp_cloud.inbound_media_cloud import hydrate_cloud_inbound_snapshot

    async def fake_download(*, access_token: str, media_id: str, max_bytes: int = 8_000_000):
        _ = access_token, media_id, max_bytes
        return b"Open 9am-5pm\nAfter care cream", "text/plain"

    monkeypatch.setattr("services.whatsapp_cloud.inbound_media_cloud._load_token", lambda _s: "tok")
    monkeypatch.setattr(
        "services.whatsapp_cloud.graph_client.download_media_bytes",
        fake_download,
    )
    snapshot = await hydrate_cloud_inbound_snapshot(
        {
            "tenant_id": "cloud-doc-shop",
            "message_type": "document",
            "media_id": "555",
            "media_mime": "text/plain",
        }
    )
    assert "After care cream" in snapshot["extract"]


@pytest.mark.asyncio
async def test_cloud_video_hydrate_stores_frame(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LINASBOT_DATA_ROOT", str(tmp_path / "data"))
    from services.whatsapp_cloud.inbound_media_cloud import hydrate_cloud_inbound_snapshot

    async def fake_download(*, access_token: str, media_id: str, max_bytes: int = 8_000_000):
        _ = access_token, media_id, max_bytes
        return b"ftypmp42", "video/mp4"

    def fake_video(_data: bytes) -> dict:
        return {
            "status": "extracted",
            "frames": [b"\xff\xd8\xff\xd9 inbound"],
            "frame_count": 1,
            "audio": b"",
        }

    monkeypatch.setattr("services.whatsapp_cloud.inbound_media_cloud._load_token", lambda _s: "tok")
    monkeypatch.setattr(
        "services.whatsapp_cloud.graph_client.download_media_bytes",
        fake_download,
    )
    monkeypatch.setattr(
        "services.customer_reply_v2.inbound_video.extract_bounded_video",
        fake_video,
    )
    snapshot = await hydrate_cloud_inbound_snapshot(
        {"tenant_id": "cloud-vid-shop", "message_type": "video", "media_id": "777"}
    )
    assert snapshot["image_media_id"].startswith("prdim_")
    assert snapshot["video_status"] == "extracted"


def test_inbound_bytes_store_resource_id(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LINASBOT_DATA_ROOT", str(tmp_path / "data"))
    user_data = {"tenant_id": "img-shop"}
    media_id = store_inbound_image(user_data, content=b"\xff\xd8\xff\xd9 inbound")
    assert media_id.startswith("prdim_")
    view = inbound_payload_from_user_data(user_data, has_image=True)
    assert view["image_media_id"] == media_id
    assert store_inbound_image(user_data, content=b"\xff\xd8\xff\xd9 inbound") == media_id


def test_whatsapp_photo_and_voice_stamp_inbound_media() -> None:
    from handlers import photo_handlers, voice_handlers
    from handlers.text_handlers_respond_phase2 import text_handlers_respond_phase2
    from modules import webhook_handlers_photo

    webhook = getsource(webhook_handlers_photo)
    assert "store_inbound_image_base64" in webhook
    assert "wrap_tracked_send" in webhook
    assert "run_reserved_customer_turn" in webhook
    assert 'user_data["_source_message_id"] = str(image_id)' in webhook
    assert "user_image_base64=base64_image" in webhook
    voice = getsource(voice_handlers.handle_voice_message)
    assert "mark_inbound_attachment(user_data, \"audio\", transcript=user_text_input)" in voice
    assert "record_pending_provider" in voice
    assert 'category="stt"' in voice
    assert "0.006" not in voice
    assert "whisper_cost" not in voice
    phase2 = getsource(text_handlers_respond_phase2)
    assert "has_image=bool(user_image_base64)" in phase2
    assert "settle_after_outbound" in phase2
    assert "settle_reserved_credits" in phase2
    photo = getsource(photo_handlers.handle_photo_message)
    assert "customer_brain_enabled()" in photo
    assert "_process_and_respond" in photo
    assert "run_reserved_customer_turn" in photo
    assert "wrap_tracked_send" in photo
    assert "store_inbound_image_from_url" in photo
    assert "store_inbound_image_base64" in photo
    assert "get_bot_photo_analysis_from_gpt" in getsource(photo_handlers)
    from services.whatsapp_cloud import ai_bridge

    wa = getsource(ai_bridge.maybe_generate_and_send_ai_reply)
    assert "inbound_from_attachment_type" in wa
    assert "inbound_media=inbound_media or None" in wa
    assert 'inbound_media["image_media_id"]' in wa
    assert "snapshot.get(\"transcript\")" in wa
    assert "extract=extract" in wa
    assert "reserve_leftover_reply" in wa
    assert "credit_ledger_service.capture" not in wa
    from services.whatsapp_cloud import webhook_processor

    assert "hydrate_cloud_inbound_snapshot" in getsource(webhook_processor._process_one_event)
    from services.omnichannel import generate as omni_generate
    from services.tiktok_business import messaging as tiktok_messaging

    omni = getsource(omni_generate)
    assert "planner_text_from_inbound" in omni
    assert "inbound_media=inbound_media or None" in omni
    tt = getsource(tiktok_messaging.handle_messaging_webhook)
    assert "hydrate_tiktok_inbound_media" in tt
    assert "inbound_media.get(\"attachment_types\")" in tt
    assert "snapshot[\"text\"]" in tt


@pytest.mark.asyncio
async def test_tiktok_hydrate_type_and_url(monkeypatch) -> None:
    from services.tiktok_business.inbound_dm import (
        attachments_from_content,
        hydrate_tiktok_inbound_media,
        message_text_from_content,
    )

    assert message_text_from_content({"text": {"body": "hi"}}) == "hi"
    assert attachments_from_content({"image": {"url": "https://cdn.example/a.jpg"}})[0]["type"] == "image"
    type_only = await hydrate_tiktok_inbound_media(
        tenant_id="shop",
        content={"message_type": "image"},
    )
    assert type_only == {"attachment_types": ["image"]}

    from services.customer_reply_v2.inbound_media import InboundMediaResult

    async def fake_ingest(**kwargs):
        return InboundMediaResult(attachment_types=["image"], image_media_id="prdim_tt")

    monkeypatch.setattr(
        "services.customer_reply_v2.inbound_media.ingest_inbound_attachments",
        fake_ingest,
    )
    hydrated = await hydrate_tiktok_inbound_media(
        tenant_id="shop",
        content={"image": {"url": "https://cdn.example/a.jpg"}},
    )
    assert hydrated.get("image_media_id") == "prdim_tt"


@pytest.mark.asyncio
async def test_store_inbound_image_from_url_uses_ssrf_fetch(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LINASBOT_DATA_ROOT", str(tmp_path / "data"))
    from services.customer_reply_v2.inbound_media import store_inbound_image_from_url

    async def fake_fetch(url: str, *, max_bytes: int, timeout_s: float | None = None):
        _ = url, max_bytes, timeout_s
        return {"ok": True, "bytes": b"\xff\xd8\xff\xd9 remote", "mime": "image/jpeg"}

    monkeypatch.setattr("services.customer_reply_v2.inbound_media.fetch_inbound_url", fake_fetch)
    user_data = {"tenant_id": "remote-shop"}
    media_id = await store_inbound_image_from_url(user_data, "https://cdn.example/photo.jpg")
    assert media_id.startswith("prdim_")
    assert user_data["inbound_image_media_id"] == media_id
