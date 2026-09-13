"""Inbound video: adaptive stills (5/10/15s) plus full-length audio for STT."""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

MAX_VIDEO_BYTES = 80 * 1024 * 1024
MAX_FRAMES = 60
MAX_ANALYZE_SECONDS = 600.0
FFMPEG_TIMEOUT_S = 180
FRAME_TIMEOUT_S = 45
AUDIO_TIMEOUT_S = 600
_DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def cap_analyze_duration_s(duration_s: float) -> tuple[float, bool]:
    """Analyze at most the first 10 minutes. Longer clips are truncated, not rejected."""
    duration = max(0.0, float(duration_s or 0.0))
    if duration <= MAX_ANALYZE_SECONDS:
        return duration, False
    return MAX_ANALYZE_SECONDS, True


def frame_interval_s(duration_s: float) -> float:
    """Small clips: 5s. Medium: 10s. Long: 15s. Duration should already be capped."""
    duration = max(0.0, float(duration_s or 0.0))
    if duration <= 60:
        return 5.0
    if duration <= 180:
        return 10.0
    return 15.0


def frame_offsets_s(duration_s: float) -> list[float]:
    """Cover the whole video. If stills would exceed MAX_FRAMES, space them evenly."""
    duration = max(0.0, float(duration_s or 0.0))
    if duration <= 0:
        return [0.0]
    interval = frame_interval_s(duration)
    needed = int(duration // interval) + 1
    if needed > MAX_FRAMES:
        interval = duration / float(MAX_FRAMES)
        needed = MAX_FRAMES
    end = max(0.0, duration - 0.05)
    offsets: list[float] = []
    for index in range(needed):
        stamp = min(round(index * interval, 2), end)
        if not offsets or stamp > offsets[-1]:
            offsets.append(stamp)
    if end > 0 and (not offsets or end - offsets[-1] >= min(2.0, interval / 2)):
        if len(offsets) < MAX_FRAMES:
            offsets.append(round(end, 2))
        else:
            offsets[-1] = round(end, 2)
    return offsets or [0.0]


def extract_bounded_video(data: bytes) -> dict[str, Any]:
    """Return jpeg frames and wav audio for the full clip. Honest if ffmpeg cannot run."""
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
        duration = _probe_duration_s(src)
        capped, truncated = cap_analyze_duration_s(duration)
        frames = _extract_frames(src, root, capped)
        audio = _extract_audio(src, root, duration_s=capped)
        if not frames and audio is None:
            return _result(status="video_extract_failed")
        status = "extracted"
        if not frames:
            status = "audio_only"
        elif audio is None:
            status = "frames_only"
        return {
            "status": status,
            "frames": frames,
            "frame_count": len(frames),
            "audio": audio,
            "duration_s": duration,
            "analyze_duration_s": capped,
            "interval_s": frame_interval_s(capped),
            "truncated": truncated,
            "error": "",
        }


def _result(*, status: str, error: str = "") -> dict[str, Any]:
    return {
        "status": status,
        "frames": [],
        "frame_count": 0,
        "audio": None,
        "duration_s": 0.0,
        "analyze_duration_s": 0.0,
        "interval_s": 5.0,
        "truncated": False,
        "error": error or status,
    }


def _run_ffmpeg(args: list[str], *, timeout_s: float = FFMPEG_TIMEOUT_S) -> subprocess.CompletedProcess[bytes] | None:
    try:
        return subprocess.run(
            args,
            check=False,
            capture_output=True,
            timeout=timeout_s,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def _probe_duration_s(src: Path) -> float:
    completed = _run_ffmpeg(["ffmpeg", "-i", str(src)], timeout_s=20)
    if completed is None:
        return 0.0
    text = (completed.stderr or b"").decode("utf-8", "replace")
    match = _DURATION_RE.search(text)
    if match is None:
        return 0.0
    hours, minutes, seconds = match.groups()
    return (int(hours) * 3600) + (int(minutes) * 60) + float(seconds)


def _extract_frames(src: Path, root: Path, duration_s: float) -> list[bytes]:
    frames: list[bytes] = []
    for index, offset in enumerate(frame_offsets_s(duration_s), start=1):
        out = root / f"frame_{index}.jpg"
        completed = _run_ffmpeg(
            [
                "ffmpeg",
                "-y",
                "-ss",
                f"{offset:.2f}",
                "-i",
                str(src),
                "-frames:v",
                "1",
                "-vf",
                "scale=480:-2",
                "-q:v",
                "5",
                str(out),
            ],
            timeout_s=FRAME_TIMEOUT_S,
        )
        if completed is not None and completed.returncode == 0 and out.is_file() and out.stat().st_size > 0:
            frames.append(out.read_bytes())
    return frames


def _extract_audio(src: Path, root: Path, *, duration_s: float) -> bytes | None:
    out = root / "audio.wav"
    args = [
        "ffmpeg",
        "-y",
        "-i",
        str(src),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
    ]
    if duration_s > 0:
        args.extend(["-t", f"{duration_s:.2f}"])
    args.append(str(out))
    completed = _run_ffmpeg(args, timeout_s=AUDIO_TIMEOUT_S)
    if completed is not None and completed.returncode == 0 and out.is_file() and out.stat().st_size > 0:
        return out.read_bytes()
    return None
