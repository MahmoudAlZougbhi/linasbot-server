"""Comment video stills: 5/10/15s by length, plus full-audio extract."""

from __future__ import annotations

from services.customer_reply_v2.inbound_video import (
    MAX_AUDIO_SECONDS,
    MAX_FRAMES,
    frame_interval_s,
    frame_offsets_s,
)


def test_short_video_uses_five_second_stills() -> None:
    assert frame_interval_s(20.0) == 5.0
    offsets = frame_offsets_s(20.0)
    assert offsets[0] == 0.0
    assert offsets[1] == 5.0
    assert offsets[2] == 10.0
    assert offsets[3] == 15.0


def test_medium_video_uses_ten_second_stills() -> None:
    assert frame_interval_s(90.0) == 10.0
    offsets = frame_offsets_s(90.0)
    assert offsets[:4] == [0.0, 10.0, 20.0, 30.0]


def test_three_minute_video_uses_fifteen_second_stills() -> None:
    assert frame_interval_s(180.0) == 15.0
    offsets = frame_offsets_s(180.0)
    assert MAX_FRAMES == 12
    assert len(offsets) == 12
    assert offsets[0] == 0.0
    assert offsets[1] == 15.0


def test_empty_duration_still_has_first_frame() -> None:
    assert frame_offsets_s(0.0) == [0.0]


def test_audio_cap_covers_full_typical_social_video() -> None:
    assert MAX_AUDIO_SECONDS >= 600
