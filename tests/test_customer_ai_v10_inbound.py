"""Customer AI V10 inbound media: image/voice/video/file/link into V2."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from services.customer_reply_v2.inbound_extract import extract_inbound_file
from services.customer_reply_v2.inbound_media import (
    ingest_inbound_attachments,
    luna_inbound_view,
)
from services.customer_reply_v2.inbound_video import extract_bounded_video
from services.ssrf_guard import SSRFValidationError, validate_fetch_url

JPEG = b"\xff\xd8\xff\xd9 inbound"
PDF = b"%PDF-1.4\n(After Care Cream) Tj\n"


@pytest.fixture()
def inbound_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("LINASBOT_DATA_ROOT", str(tmp_path / "data"))
    monkeypatch.setenv("ENVIRONMENT", "test")
    return tmp_path


@pytest.mark.asyncio
async def test_image_is_stored_and_not_generic_arabic(inbound_env: Path) -> None:
    async def fetch(url: str, max_bytes: int) -> dict:
        _ = url, max_bytes
        return {"ok": True, "bytes": JPEG, "mime": "image/jpeg", "url": "https://cdninstagram.com/a.jpg", "error": ""}

    result = await ingest_inbound_attachments(
        tenant_id="t-in",
        attachments=[{"type": "image", "payload": {"url": "https://cdninstagram.com/a.jpg"}}],
        caption="",
        fetch_url=fetch,
    )
    assert "image" in result.attachment_types
    assert result.image_media_id and result.image_media_id.startswith("prdim_")
    assert "اكتبلي شو حابب تعرف" not in result.pipeline_text
    view = luna_inbound_view(result)
    assert view["image_media_id"] == result.image_media_id
    assert "bytes" not in view
    assert "storage_key" not in view


@pytest.mark.asyncio
async def test_audio_uses_real_stt_path(inbound_env: Path) -> None:
    async def fetch(url: str, max_bytes: int) -> dict:
        _ = url, max_bytes
        return {"ok": True, "bytes": b"OggSxxxx", "mime": "audio/ogg", "url": url, "error": ""}

    async def stt(*, data: bytes, filename: str = "") -> dict:
        _ = filename
        assert data.startswith(b"OggS")
        return {"ok": True, "text": "بدي كريم after care", "model": "whisper-1", "error": ""}

    result = await ingest_inbound_attachments(
        tenant_id="t-in",
        attachments=[{"type": "audio", "payload": {"url": "https://cdninstagram.com/v.ogg"}}],
        fetch_url=fetch,
        transcribe=stt,
    )
    assert result.transcript == "بدي كريم after care"
    assert result.pipeline_text == "بدي كريم after care"
    assert luna_inbound_view(result)["transcript"] == "بدي كريم after care"
    from services.membership.expense_journal import list_events

    events = list_events(tenant_id="t-in", category="stt")
    assert events
    assert events[0].status == "pending"
    assert events[0].amount_usd is None
    assert events[0].model == "whisper-1"


@pytest.mark.asyncio
async def test_video_frames_and_audio_not_unimplemented(inbound_env: Path) -> None:
    async def fetch(url: str, max_bytes: int) -> dict:
        _ = url, max_bytes
        return {"ok": True, "bytes": b"ftypmp42", "mime": "video/mp4", "url": url, "error": ""}

    def extract(_data: bytes) -> dict:
        return {
            "status": "extracted",
            "frames": [JPEG],
            "frame_count": 1,
            "audio": b"RIFFWAVEdata",
            "error": "",
        }

    async def stt(*, data: bytes, filename: str = "") -> dict:
        _ = filename
        assert data.startswith(b"RIFF")
        return {"ok": True, "text": "laser hair removal", "model": "whisper-1", "error": ""}

    result = await ingest_inbound_attachments(
        tenant_id="t-in",
        attachments=[{"type": "video", "payload": {"url": "https://cdninstagram.com/v.mp4"}}],
        fetch_url=fetch,
        extract_video=extract,
        transcribe=stt,
    )
    assert result.video_status == "extracted"
    assert result.video_frame_count == 1
    assert result.image_media_id
    assert result.transcript == "laser hair removal"
    assert "NOT IMPLEMENTED" not in json.dumps(luna_inbound_view(result))


def test_video_honest_when_ffmpeg_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("services.customer_reply_v2.inbound_video.ffmpeg_available", lambda: False)
    out = extract_bounded_video(b"not-a-real-mp4-but-nonempty")
    assert out["status"] == "ffmpeg_unavailable"
    assert out["frame_count"] == 0
    assert "NOT IMPLEMENTED" not in str(out)


def test_pdf_and_txt_extract() -> None:
    pdf = extract_inbound_file(data=PDF, mime="application/pdf", filename="care.pdf")
    assert "After Care Cream" in pdf["text"]
    txt = extract_inbound_file(data=b"hello inbound file", mime="text/plain", filename="note.txt")
    assert txt["text"] == "hello inbound file"


@pytest.mark.asyncio
async def test_file_attachment_extracts_pdf(inbound_env: Path) -> None:
    async def fetch(url: str, max_bytes: int) -> dict:
        _ = url, max_bytes
        return {"ok": True, "bytes": PDF, "mime": "application/pdf", "url": url, "error": ""}

    result = await ingest_inbound_attachments(
        tenant_id="t-in",
        attachments=[{"type": "file", "payload": {"url": "https://cdninstagram.com/a.pdf", "filename": "care.pdf"}}],
        fetch_url=fetch,
    )
    assert "file" in result.attachment_types
    assert "After Care Cream" in result.extract


def test_link_ssrf_blocked() -> None:
    with pytest.raises(SSRFValidationError):
        validate_fetch_url("http://127.0.0.1/secret")
    with pytest.raises(SSRFValidationError):
        validate_fetch_url("https://169.254.169.254/latest/meta-data")


@pytest.mark.asyncio
async def test_inbound_link_ssrf_does_not_fetch(inbound_env: Path) -> None:
    called = {"n": 0}

    async def fetch(url: str, max_bytes: int) -> dict:
        called["n"] += 1
        return {"ok": True, "bytes": b"x", "mime": "text/html", "url": url, "error": ""}

    result = await ingest_inbound_attachments(
        tenant_id="t-in",
        attachments=[{"type": "share", "payload": {"url": "http://127.0.0.1/x"}}],
        fetch_url=fetch,
    )
    assert called["n"] == 0
    assert result.inbound_link == ""
    assert any("ssrf" in err for err in result.fetch_errors)


def test_social_processor_no_generic_image_placeholder() -> None:
    src = Path("services/social_messaging_processor.py").read_text(encoding="utf-8")
    assert "اكتبلي شو حابب تعرف" not in src
    assert "ingest_inbound_attachments" in src


def test_whatsapp_public_availability_stays_off(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.whatsapp_cloud.config import get_whatsapp_cloud_flags

    monkeypatch.setenv("WHATSAPP_CLOUD_PUBLIC_AVAILABILITY", "false")
    flags = get_whatsapp_cloud_flags()
    assert flags.public_availability is False
    webhook = Path("modules/webhook_handlers.py").read_text(encoding="utf-8")
    assert "whatsapp_inbound_ai_disabled" in webhook


def test_image_candidates_remain_clamped_3_to_8() -> None:
    from services.products.crv2_tools import _clamp_image_top_k

    assert _clamp_image_top_k(1) == 3
    assert _clamp_image_top_k(10) == 8
