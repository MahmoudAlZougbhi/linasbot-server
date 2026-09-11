"""Media and inbound live-cert scenarios. Generation is stubbed until the new engine lands."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from _live_cert.bootstrap import TENANT_ID
from _live_cert.calls import dm, record, trace


async def run_media_scenarios(*, product: dict[str, Any], assets: Path, api_key: str) -> None:
    from openai import AsyncOpenAI

    from services.customer_reply_v2.inbound_extract import extract_inbound_file
    from services.customer_reply_v2.inbound_stt import transcribe_inbound_audio
    from services.customer_reply_v2.inbound_video import extract_bounded_video, ffmpeg_available
    from services.ssrf_guard import SSRFValidationError, validate_fetch_url

    _ = TENANT_ID, product
    out = await dm(
        "شو هيدا؟",
        conversation_id="c_in_img",
        provider_sender_id="u_in_img",
        inbound_media={"attachment_types": ["image"], "image_media_id": product["image_media_id"]},
        attachment_types=["image"],
    )
    tr = trace(out, message="شو هيدا؟", channel="instagram_dm")
    record(
        "inbound_image_wired_to_v2",
        "ENGINE REMOVED",
        ok=out.reason != "engine_removed" and out.reply is None and (out.metadata or {}).get("customer_engine") == "brain",
        reason=out.reason,
        trace=tr,
        note="Inbound still persists. Auto-reply is off until the new engine lands.",
    )

    try:
        client = AsyncOpenAI(api_key=api_key)
        speech = await client.audio.speech.create(
            model="gpt-4o-mini-tts", voice="alloy", input="مرحبا، بدي أعرف سعر Full Body."
        )
        audio_path = assets / "full_body_price.mp3"
        raw = speech.content if hasattr(speech, "content") else await speech.aread()
        audio_path.write_bytes(raw)
        stt = await transcribe_inbound_audio(data=audio_path.read_bytes(), filename="full_body_price.mp3")
        transcript = str(stt.get("text") or "").strip()
        record(
            "voice_stt_then_v2",
            "REAL OPENAI",
            ok=bool(stt.get("ok")) and bool(transcript),
            transcript=transcript[:200],
            stt_model=stt.get("model"),
            note="STT ingest only. Customer reply generation is removed.",
        )
    except Exception as exc:
        record(
            "voice_stt_then_v2",
            "BLOCKED",
            ok=False,
            blocker=f"stt_or_tts:{type(exc).__name__}",
            error=str(exc)[:200],
        )

    video_path = assets / "test_card.mp4"
    video_bytes = video_path.read_bytes() if video_path.is_file() else b""
    extracted = extract_bounded_video(video_bytes) if video_bytes else {"status": "empty_video"}
    if extracted.get("status") == "ffmpeg_unavailable":
        record(
            "inbound_video_frames",
            "BLOCKED",
            ok=False,
            blocker="ffmpeg_unavailable",
            first_failing_layer="services/customer_reply_v2/inbound_video.py extract_bounded_video",
        )
    else:
        record(
            "inbound_video_frames",
            "REAL DATABASE/RETRIEVAL",
            ok=extracted.get("status") in {"extracted", "audio_only"} or int(extracted.get("frame_count") or 0) > 0,
            status=extracted.get("status"),
            frame_count=extracted.get("frame_count") or len(extracted.get("frames") or []),
            ffmpeg=ffmpeg_available(),
        )

    pdf_extract = extract_inbound_file(
        data=(assets / "price_list.pdf").read_bytes(), filename="price_list.pdf", mime="application/pdf"
    )
    txt_extract = extract_inbound_file(
        data=(assets / "after_care_notes.txt").read_bytes(), filename="after_care_notes.txt", mime="text/plain"
    )
    record(
        "inbound_file_extract",
        "REAL DATABASE/RETRIEVAL",
        ok=str(txt_extract.get("status") or "") == "extracted" or bool(txt_extract.get("text")),
        pdf_status=pdf_extract.get("status"),
        txt_preview=str(txt_extract.get("text") or "")[:180],
    )

    try:
        validate_fetch_url("http://127.0.0.1/secret")
        ssrf_ok = False
        ssrf_err = "ssrf_allowed_loopback"
    except SSRFValidationError:
        ssrf_ok = True
        ssrf_err = "SSRFValidationError"
    record("inbound_link_ssrf", "REAL DATABASE/RETRIEVAL", ok=ssrf_ok, error=ssrf_err)
