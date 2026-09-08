"""Phone voice notes must keep a real mime — never fake audio/webm."""

from __future__ import annotations

import base64

from utils.utils_voice_convert import (
    prepare_operator_voice_upload,
    sniff_audio_format,
)


def test_sniff_m4a_ftyp() -> None:
    data = b"\x00\x00\x00\x20ftypM4A " + b"\x00" * 24
    assert sniff_audio_format(data) == "mp4"


def test_sniff_webm_ogg_wav() -> None:
    assert sniff_audio_format(b"\x1aE\xdf\xa3" + b"\x00" * 8) == "webm"
    assert sniff_audio_format(b"OggS" + b"\x00" * 8) == "ogg"
    assert sniff_audio_format(b"RIFF" + b"\x00" * 4 + b"WAVE") == "wav"


def test_prepare_m4a_does_not_label_webm() -> None:
    raw = b"\x00\x00\x00\x20ftypM4A " + b"\x00" * 40
    out = prepare_operator_voice_upload(base64.b64encode(raw).decode(), user_id="96170123456")
    assert out["mime"] == "audio/mp4"
    assert out["filename"].endswith(".m4a")
    assert ".webm" not in out["filename"]


def test_prepare_strips_data_uri() -> None:
    raw = b"\x00\x00\x00\x18ftypisom" + b"\x00" * 20
    payload = "data:audio/mp4;base64," + base64.b64encode(raw).decode()
    out = prepare_operator_voice_upload(payload, user_id="u1")
    assert out["mime"] == "audio/mp4"
    assert base64.b64decode(out["payload"]) == raw
