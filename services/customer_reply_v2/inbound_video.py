"""Bounded inbound video: up to 3 frames + audio track. Honest status if ffmpeg is missing."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

MAX_VIDEO_BYTES = 12 * 1024 * 1024
MAX_FRAMES = 3
FRAME_OFFSETS_S = (0.0, 1.0, 2.0)
FFMPEG_TIMEOUT_S = 20


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def extract_bounded_video(data: bytes) -> dict[str, Any]:
    """Return jpeg frames and optional wav audio. Never claims frames if ffmpeg cannot run."""
    raw = data or b""
    if not raw:
        return _result(status="empty_video")
    if len(raw) > MAX_VIDEO_BYTES:
        return _result(status="video_too_large")
    if not ffmpeg_available():
        return _result(status="ffmpeg_unavailable")
    with tempfile.TemporaryDirectory(prefix="linas_invid_") as tmp:
        root = Path(tmp)
        src = root / "in.bin"
        src.write_bytes(raw)
        frames = _extract_frames(src, root)
        audio = _extract_audio(src, root)
        if not frames and audio is None:
            return _result(status="video_extract_failed")
        status = "extracted"
        if not frames:
            status = "audio_only"
        elif audio is None:
            status = "frames_only"
        return {
            "status": status,
            "frames": frames[:MAX_FRAMES],
            "frame_count": len(frames[:MAX_FRAMES]),
            "audio": audio,
            "error": "",
        }


def _result(*, status: str, error: str = "") -> dict[str, Any]:
    return {"status": status, "frames": [], "frame_count": 0, "audio": None, "error": error or status}


def _run_ffmpeg(args: list[str]) -> bool:
    try:
        completed = subprocess.run(
            args,
            check=False,
            capture_output=True,
            timeout=FFMPEG_TIMEOUT_S,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


def _extract_frames(src: Path, root: Path) -> list[bytes]:
    frames: list[bytes] = []
    for index, offset in enumerate(FRAME_OFFSETS_S[:MAX_FRAMES], start=1):
        out = root / f"frame_{index}.jpg"
        ok = _run_ffmpeg(
            [
                "ffmpeg",
                "-y",
                "-ss",
                f"{offset:.2f}",
                "-i",
                str(src),
                "-frames:v",
                "1",
                "-q:v",
                "5",
                str(out),
            ]
        )
        if ok and out.is_file() and out.stat().st_size > 0:
            frames.append(out.read_bytes())
    return frames


def _extract_audio(src: Path, root: Path) -> bytes | None:
    out = root / "audio.wav"
    ok = _run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(src),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-t",
            "30",
            str(out),
        ]
    )
    if ok and out.is_file() and out.stat().st_size > 0:
        return out.read_bytes()
    return None
