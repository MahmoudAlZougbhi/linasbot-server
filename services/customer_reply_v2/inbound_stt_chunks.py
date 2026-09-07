"""Transcribe a full WAV by splitting under the provider size cap. Never invent text."""

from __future__ import annotations

import io
import wave
from typing import Any

from services.customer_reply_v2.inbound_stt import MAX_AUDIO_BYTES, transcribe_inbound_audio

CHUNK_SECONDS = 480
SAFE_CHUNK_BYTES = 20 * 1024 * 1024


def split_wav_chunks(
    data: bytes,
    *,
    chunk_seconds: int = CHUNK_SECONDS,
    max_bytes: int = SAFE_CHUNK_BYTES,
) -> list[bytes]:
    raw = data or b""
    if not raw:
        return []
    if len(raw) <= max_bytes:
        return [raw]
    try:
        with wave.open(io.BytesIO(raw), "rb") as handle:
            channels = handle.getnchannels()
            width = handle.getsampwidth()
            rate = handle.getframerate()
            frames = handle.readframes(handle.getnframes())
    except wave.Error:
        return [raw] if len(raw) <= MAX_AUDIO_BYTES else []
    frame_bytes = max(1, channels * width)
    step = max(frame_bytes, int(rate * chunk_seconds) * frame_bytes)
    chunks: list[bytes] = []
    for start in range(0, len(frames), step):
        piece = frames[start : start + step]
        if not piece:
            continue
        buf = io.BytesIO()
        with wave.open(buf, "wb") as out:
            out.setnchannels(channels)
            out.setsampwidth(width)
            out.setframerate(rate)
            out.writeframes(piece)
        chunks.append(buf.getvalue())
    return chunks or [raw]


async def transcribe_full_wav(data: bytes) -> dict[str, Any]:
    parts = split_wav_chunks(data)
    if not parts:
        return {"ok": False, "error": "audio_too_large", "text": "", "model": ""}
    texts: list[str] = []
    model = ""
    last_error = ""
    for index, chunk in enumerate(parts, start=1):
        spoken = await transcribe_inbound_audio(data=chunk, filename=f"comment_video_{index}.wav")
        model = str(spoken.get("model") or model)
        if spoken.get("ok") and spoken.get("text"):
            texts.append(str(spoken["text"]).strip())
        else:
            last_error = str(spoken.get("error") or last_error)
    text = " ".join(part for part in texts if part).strip()
    if text:
        return {"ok": True, "text": text, "model": model, "error": ""}
    return {"ok": False, "error": last_error or "no_speech_detected", "text": "", "model": model}
