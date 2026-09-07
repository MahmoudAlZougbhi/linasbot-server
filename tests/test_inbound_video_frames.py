"""Adaptive comment stills: 5s / 10s / 15s across the whole video, no 3-minute cut."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import pytest

from services.customer_reply_v2.inbound_video import (
    MAX_FRAMES,
    extract_bounded_video,
    ffmpeg_available,
    frame_interval_s,
    frame_offsets_s,
)


def test_short_video_uses_five_second_interval() -> None:
    assert frame_interval_s(12.0) == 5.0
    assert frame_interval_s(60.0) == 5.0
    offsets = frame_offsets_s(12.0)
    assert offsets[0] == 0.0
    assert 5.0 in offsets
    assert offsets[-1] >= 10.0


def test_medium_video_uses_ten_second_interval() -> None:
    assert frame_interval_s(61.0) == 10.0
    assert frame_interval_s(180.0) == 10.0
    offsets = frame_offsets_s(120.0)
    assert offsets[0] == 0.0
    assert offsets[1] == 10.0
    assert offsets[-1] >= 110.0


def test_long_video_uses_fifteen_second_interval() -> None:
    assert frame_interval_s(181.0) == 15.0
    offsets = frame_offsets_s(240.0)
    assert offsets[0] == 0.0
    assert offsets[1] == 15.0
    assert offsets[-1] >= 220.0


def test_very_long_video_covers_full_length_within_frame_cap() -> None:
    offsets = frame_offsets_s(20 * 60)
    assert len(offsets) == MAX_FRAMES
    assert offsets[0] == 0.0
    assert offsets[-1] >= 1100.0


def test_empty_duration_still_has_first_frame() -> None:
    assert frame_offsets_s(0.0) == [0.0]


def test_ffmpeg_extracts_full_audio_and_five_second_stills() -> None:
    if not ffmpeg_available():
        pytest.skip("ffmpeg is required for comment video stills")
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "clip.mp4"
        made = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "color=c=blue:s=320x240:d=12",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=440:duration=12",
                "-shortest",
                "-pix_fmt",
                "yuv420p",
                str(src),
            ],
            check=False,
            capture_output=True,
            timeout=30,
        )
        assert made.returncode == 0 and src.is_file(), made.stderr.decode("utf-8", "replace")[-500:]
        extracted = extract_bounded_video(src.read_bytes())
        assert extracted["status"] == "extracted"
        assert extracted["interval_s"] == 5.0
        assert extracted["frame_count"] >= 3
        assert extracted["audio"]
        assert len(extracted["audio"]) > 1000
