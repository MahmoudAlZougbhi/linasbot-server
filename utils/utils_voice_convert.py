"""Sniff phone voice formats and convert to WhatsApp-friendly audio when needed."""

from __future__ import annotations

import base64
import io
import time

# WhatsApp Cloud accepts these without a forced Opus remux.
_WHATSAPP_NATIVE = frozenset({"ogg", "mp4", "mp3", "aac", "amr"})
_TRY_FORMATS = ("mp4", "m4a", "webm", "3gp", "caf", "mp3", "wav", "ogg", "aac")


def decode_audio_payload(payload: str) -> bytes:
    raw = str(payload or "").strip()
    if raw.startswith("data:") and "," in raw:
        raw = raw.split(",", 1)[1]
    return base64.b64decode(raw)


def sniff_audio_format(data: bytes) -> str:
    if not data:
        return ""
    if data[:4] == b"OggS":
        return "ogg"
    if data[:4] == b"fLaC":
        return "flac"
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return "wav"
    if data[:4] == b"\x1aE\xdf\xa3":
        return "webm"
    if data[:4] == b"caff":
        return "caf"
    if len(data) >= 12 and data[4:8] == b"ftyp":
        brand = data[8:12]
        if brand[:3] == b"3gp":
            return "3gp"
        return "mp4"
    if data[:3] == b"ID3":
        return "mp3"
    if len(data) >= 2 and data[0] == 0xFF and (data[1] & 0xE0) == 0xE0:
        return "mp3"
    return ""


def mime_for_audio_format(fmt: str) -> str:
    return {
        "ogg": "audio/ogg",
        "webm": "audio/webm",
        "mp4": "audio/mp4",
        "m4a": "audio/mp4",
        "mp3": "audio/mpeg",
        "wav": "audio/wav",
        "caf": "audio/x-caf",
        "3gp": "audio/3gpp",
        "aac": "audio/aac",
        "amr": "audio/amr",
        "flac": "audio/flac",
    }.get(fmt, "audio/mp4")


def ext_for_audio_format(fmt: str) -> str:
    return {
        "mp4": "m4a",
        "m4a": "m4a",
        "mpeg": "mp3",
        "3gpp": "3gp",
    }.get(fmt, fmt or "m4a")


def convert_voice_to_opus(base64_audio: str, hinted_format: str = "") -> tuple[str, str | None, str]:
    """Remux to OGG/Opus. Returns (base64, ogg_name_or_none, mime)."""
    raw = decode_audio_payload(base64_audio)
    sniffed = sniff_audio_format(raw)
    hint = str(hinted_format or "").strip().lower()
    if hint == "m4a":
        hint = "mp4"
    candidates: list[str] = []
    for fmt in (hint, sniffed, *_TRY_FORMATS):
        if fmt and fmt not in candidates:
            candidates.append(fmt)
    fallback_mime = mime_for_audio_format(sniffed or hint or "mp4")
    try:
        from pydub import AudioSegment
    except Exception:
        return base64_audio, None, fallback_mime

    last_err: Exception | None = None
    for fmt in candidates:
        try:
            audio = AudioSegment.from_file(io.BytesIO(raw), format=fmt)
            ogg_buffer = io.BytesIO()
            audio.export(
                ogg_buffer,
                format="ogg",
                codec="libopus",
                bitrate="128k",
                parameters=["-vbr", "on", "-compression_level", "10"],
            )
            ogg_bytes = ogg_buffer.getvalue()
            file_name = f"voice_{int(time.time())}.ogg"
            return base64.b64encode(ogg_bytes).decode("utf-8"), file_name, "audio/ogg"
        except Exception as exc:
            last_err = exc
    if last_err:
        print(f"⚠️ Voice convert to Opus failed: {last_err}")
    return base64_audio, None, fallback_mime


def prepare_operator_voice_upload(payload: str, *, user_id: str) -> dict[str, str]:
    """Keep phone m4a as-is. Only remux formats WhatsApp Cloud will not accept."""
    raw = decode_audio_payload(payload)
    clean_b64 = base64.b64encode(raw).decode("utf-8") if raw else str(payload or "")
    fmt = sniff_audio_format(raw)
    stamp = int(time.time())
    uid = str(user_id or "op")[-8:]
    if fmt in _WHATSAPP_NATIVE:
        return {
            "payload": clean_b64,
            "filename": f"voice_{uid}_{stamp}.{ext_for_audio_format(fmt)}",
            "mime": mime_for_audio_format(fmt),
        }
    converted, ogg_name, out_mime = convert_voice_to_opus(clean_b64, hinted_format=fmt)
    if ogg_name:
        return {"payload": converted, "filename": ogg_name, "mime": "audio/ogg"}
    fallback = fmt or "mp4"
    return {
        "payload": clean_b64,
        "filename": f"voice_{uid}_{stamp}.{ext_for_audio_format(fallback)}",
        "mime": mime_for_audio_format(fallback),
    }
