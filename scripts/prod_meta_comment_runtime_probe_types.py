"""Shared types, constants, and helpers for the Meta runtime probe."""

from __future__ import annotations

import base64
import json
import os
import re
import stat
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

PATTERNS = {
    "ig_login_webhook_auth": (
        r"\[instagram-login\] webhook_authenticated object=instagram parsed=\d+ "
        r"accepted=\d+ duplicates=\d+ comments=\d+\s*$"
    ),
    "ig_login_comments_nonzero": r"\[instagram-login\] webhook_authenticated .* comments=[1-9]\d*",
    "meta_comment_webhook_auth": r"\[meta-comment\] webhook_authenticated",
    "meta_comment_events_dropped": r"\[meta-comment\] events_dropped",
    "meta_comment_started": r"\[meta-comment\] event_processing_started",
    "meta_comment_completed": r"\[meta-comment\] event_processing_completed",
    "meta_comment_failed": r"\[meta-comment\] event_processing_failed",
    "meta_comment_reply_sent": r"\[meta-comment\] reply_sent",
    "meta_comment_reply_failed": r"\[meta-comment\] reply_failed",
    "meta_comment_private_reply": r"\[meta-comment\] private_reply",
    "ig_login_background_fail": r"\[instagram-login\] background_processing_failed",
    "nginx_ig_login_post": r"POST /webhook/instagram-login",
    "nginx_meta_messaging_post": r"POST /webhook/meta-messaging",
    "fb_dm_send_accepted": (
        r"(?:\[meta-evidence\] dm_send_accepted channel=facebook "
        r"auth_flow=facebook_login execution=(?:inline_meta|queue)|"
        r"\[meta-evidence-v2\] event surface=facebook_dm outcome=provider_accepted "
        r"event_id=ibe_[0-9a-f]{40})\s*$"
    ),
    "ig_dm_send_accepted": (
        r"(?:\[meta-evidence\] dm_send_accepted channel=instagram "
        r"auth_flow=instagram_login execution=(?:inline_instagram_login|queue)|"
        r"\[meta-evidence-v2\] event surface=instagram_dm outcome=provider_accepted "
        r"event_id=ibe_[0-9a-f]{40})\s*$"
    ),
    "fb_comment_reply_sent": (
        r"(?:\[meta-evidence\] comment_reply_sent channel=facebook "
        r"auth_flow=facebook_login execution=(?:inline_meta|queue)|"
        r"\[meta-evidence-v2\] event surface=facebook_comment outcome=provider_accepted "
        r"event_id=ibe_[0-9a-f]{40})\s*$"
    ),
    "ig_comment_reply_sent": (
        r"(?:\[meta-evidence\] comment_reply_sent channel=instagram "
        r"auth_flow=instagram_login execution=(?:inline_instagram_login|queue)|"
        r"\[meta-evidence-v2\] event surface=instagram_comment outcome=provider_accepted "
        r"event_id=ibe_[0-9a-f]{40})\s*$"
    ),
}

# This is intentionally a coarse diagnostic inventory.  It cannot satisfy the
# correlated controlled-test gate below because it is not event-specific.
REQUIRED_EVIDENCE = {
    "dedicated_instagram_callback_authenticated": "ig_login_webhook_auth",
    "facebook_dm_provider_accepted": "fb_dm_send_accepted",
    "direct_instagram_dm_provider_accepted": "ig_dm_send_accepted",
    "facebook_comment_reply_provider_accepted": "fb_comment_reply_sent",
    "instagram_comment_reply_provider_accepted": "ig_comment_reply_sent",
}

CONTROLLED_SCHEMA: Final = "linas-meta-controlled-evidence-v2"
FAILOVER_SCHEMA: Final = "linas-meta-controlled-failover-v1"
CONTROLLED_SURFACES: Final[tuple[str, ...]] = (
    "facebook_dm",
    "instagram_dm",
    "facebook_comment",
    "instagram_comment",
)
CONTROLLED_OUTCOMES: Final[frozenset[str]] = frozenset(
    {
        "instagram_login_authenticated",
        "provider_accepted",
        "duplicate_suppressed",
        "retry",
        "failed",
        "second_send",
    }
)
FORBIDDEN_CONTROLLED_OUTCOMES: Final[frozenset[str]] = frozenset({"retry", "failed", "second_send"})
MIN_RETRY_OBSERVATION_SECONDS: Final = 300
MAX_CONTROLLED_WINDOW_SECONDS: Final = 3600
MAX_CHECK_DELAY_SECONDS: Final = 600
MAX_MANIFEST_BYTES: Final = 65_536
MAX_ATTESTATION_BYTES: Final = 65_536
NODE_VERIFICATION_KEYS_FILE: Final = "/var/lib/linasbot/meta-ha/node-verification-keys.env"
REQUIRED_NODES: Final[tuple[str, str]] = ("node01", "node02")
_EVENT_ID_RE: Final[re.Pattern[str]] = re.compile(r"ibe_[0-9a-f]{40}")
_RELEASE_SHA_RE: Final[re.Pattern[str]] = re.compile(r"[0-9a-f]{40}")
_RUN_ID_RE: Final[re.Pattern[str]] = re.compile(r"mtr_[0-9a-f]{64}")
_FAILOVER_TX_RE: Final[re.Pattern[str]] = re.compile(r"mft_[0-9a-f]{64}")
_MANIFEST_SHA_RE: Final[re.Pattern[str]] = re.compile(r"[0-9a-f]{64}")
_DIGEST_RE: Final[re.Pattern[str]] = re.compile(r"[0-9a-f]{64}")
_PEER_RE: Final[re.Pattern[str]] = re.compile(r"[A-Za-z0-9.-]+")
_UTC_TIMESTAMP_RE: Final[re.Pattern[str]] = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z")
_CONTROLLED_MARKER_RE: Final[re.Pattern[str]] = re.compile(
    r"\[meta-evidence-v2\] event "
    r"surface=(facebook_dm|instagram_dm|facebook_comment|instagram_comment) "
    r"outcome=(instagram_login_authenticated|provider_accepted|duplicate_suppressed|retry|failed|second_send) "
    r"event_id=(ibe_[0-9a-f]{40})\s*$"
)
_JOURNAL_UNITS: Final[tuple[str, ...]] = (
    "linasbot.service",
    "linasbot-worker@high_priority.service",
    "linasbot-worker@interactive.service",
    "linasbot-worker@background.service",
    "linasbot-worker@expensive.service",
)


class ControlledEvidenceError(RuntimeError):
    """A fixed, non-sensitive reason for failing the controlled evidence gate."""


@dataclass(frozen=True)
class ControlledManifest:
    test_run_id: str
    release_sha: str
    start: datetime
    initial_cutoff: datetime
    final_cutoff: datetime
    retry_observation_seconds: int
    events: Mapping[str, str]
    bindings: Mapping[str, str]
    failover_transaction_id: str
    initial_node: str
    replay_node: str


@dataclass(frozen=True)
class FailoverAttestation:
    phase: str
    transaction_id: str
    test_run_id: str
    manifest_sha256: str
    release_sha: str
    initial_node: str
    replay_node: str
    lb_ready_projection_sha256: str
    lb_pre_attestation_sha256: str
    lb_post_attestation_sha256: str
    lb_post_observed_at: datetime
    phase_started_at: datetime
    phase_proved_at: datetime
    minimum_drain_seconds: int


@dataclass(frozen=True)
class ControlledMarker:
    node: str
    occurred_at: datetime
    surface: str
    outcome: str
    event_id: str


def scan_evidence(lines: Iterable[str]) -> Counter[str]:
    """Count only fixed coarse markers; never copy source log lines to output."""

    compiled = {name: re.compile(pattern, re.IGNORECASE) for name, pattern in PATTERNS.items()}
    return Counter(name for line in lines for name, pattern in compiled.items() if pattern.search(line))


def missing_required_evidence(counts: Counter[str]) -> list[str]:
    return [label for label, counter_name in REQUIRED_EVIDENCE.items() if counts[counter_name] < 1]


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ControlledEvidenceError("manifest_duplicate_key")
        value[key] = item
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], *, reason: str) -> None:
    if set(value) != expected:
        raise ControlledEvidenceError(reason)


def _parse_utc_timestamp(value: object, *, reason: str) -> datetime:
    if not isinstance(value, str) or _UTC_TIMESTAMP_RE.fullmatch(value) is None:
        raise ControlledEvidenceError(reason)
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ControlledEvidenceError(reason) from exc
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise ControlledEvidenceError(reason)
    return parsed.astimezone(UTC)


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _decode_base64url(value: object, *, reason: str) -> bytes:
    if not isinstance(value, str) or not value or "=" in value:
        raise ControlledEvidenceError(reason)
    try:
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (ValueError, TypeError) as exc:
        raise ControlledEvidenceError(reason) from exc
    if base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=") != value:
        raise ControlledEvidenceError(reason)
    return raw


def _iso_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _read_fd_limited(
    fd: int,
    *,
    max_bytes: int = MAX_MANIFEST_BYTES,
    size_reason: str = "manifest_size_invalid",
) -> bytes:
    chunks: list[bytes] = []
    remaining = max_bytes + 1
    while remaining > 0:
        chunk = os.read(fd, min(remaining, 8192))
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    raw = b"".join(chunks)
    if len(raw) > max_bytes:
        raise ControlledEvidenceError(size_reason)
    return raw


def _read_root_owned_bytes(
    source: str,
    *,
    max_bytes: int,
    unavailable_reason: str,
    security_reason: str,
    size_reason: str,
) -> bytes:
    path = Path(source)
    if not path.is_absolute():
        raise ControlledEvidenceError(unavailable_reason)
    try:
        before = os.lstat(path)
    except OSError as exc:
        raise ControlledEvidenceError(unavailable_reason) from exc
    if (
        not stat.S_ISREG(before.st_mode)
        or before.st_uid != 0
        or stat.S_IMODE(before.st_mode) != 0o600
        or before.st_nlink != 1
    ):
        raise ControlledEvidenceError(security_reason)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise ControlledEvidenceError(unavailable_reason) from exc
    try:
        opened = os.fstat(fd)
        if (
            opened.st_dev != before.st_dev
            or opened.st_ino != before.st_ino
            or not stat.S_ISREG(opened.st_mode)
            or opened.st_uid != 0
            or stat.S_IMODE(opened.st_mode) != 0o600
            or opened.st_nlink != 1
        ):
            raise ControlledEvidenceError(security_reason)
        try:
            raw = _read_fd_limited(fd, max_bytes=max_bytes, size_reason=size_reason)
        except OSError as exc:
            raise ControlledEvidenceError(unavailable_reason) from exc
    finally:
        os.close(fd)
    if len(raw) > max_bytes:
        raise ControlledEvidenceError(size_reason)
    return raw
