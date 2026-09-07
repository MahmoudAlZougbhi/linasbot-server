"""Full-video STT concatenates chunk transcripts and never invents text."""

from __future__ import annotations

import io
import wave

import pytest

from services.customer_reply_v2.inbound_stt_chunks import split_wav_chunks, transcribe_full_wav


def _silent_wav(*, seconds: int, rate: int = 16000) -> bytes:
    frames = b"\x00\x00" * (rate * seconds)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(frames)
    return buf.getvalue()


def test_short_wav_stays_one_chunk() -> None:
    data = _silent_wav(seconds=2)
    assert split_wav_chunks(data) == [data]


def test_long_wav_splits_under_size_cap() -> None:
    data = _silent_wav(seconds=3)
    parts = split_wav_chunks(data, chunk_seconds=1, max_bytes=1)
    assert len(parts) == 3
    assert all(part.startswith(b"RIFF") for part in parts)


@pytest.mark.asyncio
async def test_full_wav_joins_chunk_text(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []

    async def _fake(*, data: bytes, filename: str) -> dict:
        seen.append(filename)
        return {"ok": True, "text": f"part-{filename}", "model": "whisper-1", "error": ""}

    monkeypatch.setattr("services.customer_reply_v2.inbound_stt_chunks.transcribe_inbound_audio", _fake)
    data = _silent_wav(seconds=3)
    spoken = await transcribe_full_wav(data)
    assert spoken["ok"] is True
    assert "part-comment_video_1.wav" in spoken["text"]
    assert seen


@pytest.mark.asyncio
async def test_full_wav_fails_closed_when_no_speech(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _empty(*, data: bytes, filename: str) -> dict:
        _ = data, filename
        return {"ok": False, "text": "", "model": "whisper-1", "error": "no_speech_detected"}

    monkeypatch.setattr("services.customer_reply_v2.inbound_stt_chunks.transcribe_inbound_audio", _empty)
    spoken = await transcribe_full_wav(_silent_wav(seconds=1))
    assert spoken["ok"] is False
    assert spoken["text"] == ""
    assert spoken["error"] == "no_speech_detected"
