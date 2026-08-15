#!/usr/bin/env python3
"""Read-only, redacted diagnostics and correlated Meta controlled-test proof."""

from __future__ import annotations

import argparse
import base64
import glob
import hashlib
import hmac
import json
import os
import re
import stat
import subprocess
import sys
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

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


def _read_tail(path: Path, *, max_bytes: int = 4_000_000) -> list[str]:
    try:
        with path.open("rb") as handle:
            handle.seek(0, 2)
            size = handle.tell()
            handle.seek(max(0, size - max_bytes))
            return handle.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return []


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


def parse_controlled_manifest(raw: bytes) -> ControlledManifest:
    """Parse a closed-schema manifest containing hashes and timestamps only."""

    if not raw or len(raw) > MAX_MANIFEST_BYTES:
        raise ControlledEvidenceError("manifest_size_invalid")
    try:
        decoded = raw.decode("utf-8")
        document = json.loads(decoded, object_pairs_hook=_reject_duplicate_json_keys)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ControlledEvidenceError("manifest_json_invalid") from exc
    if not isinstance(document, dict):
        raise ControlledEvidenceError("manifest_shape_invalid")
    _exact_keys(
        document,
        {
            "schema",
            "test_run_id",
            "release_sha",
            "window",
            "retry_observation_seconds",
            "events",
            "bindings",
            "topology",
        },
        reason="manifest_fields_invalid",
    )
    if document["schema"] != CONTROLLED_SCHEMA:
        raise ControlledEvidenceError("manifest_schema_invalid")
    test_run_id = str(document["test_run_id"])
    release_sha = str(document["release_sha"])
    if _RUN_ID_RE.fullmatch(test_run_id) is None:
        raise ControlledEvidenceError("manifest_test_run_id_invalid")
    if _RELEASE_SHA_RE.fullmatch(release_sha) is None:
        raise ControlledEvidenceError("manifest_release_sha_invalid")

    raw_window = document["window"]
    if not isinstance(raw_window, dict):
        raise ControlledEvidenceError("manifest_window_invalid")
    _exact_keys(raw_window, {"start", "initial_cutoff", "final_cutoff"}, reason="manifest_window_fields_invalid")
    start = _parse_utc_timestamp(raw_window["start"], reason="manifest_window_start_invalid")
    initial_cutoff = _parse_utc_timestamp(raw_window["initial_cutoff"], reason="manifest_initial_cutoff_invalid")
    final_cutoff = _parse_utc_timestamp(raw_window["final_cutoff"], reason="manifest_final_cutoff_invalid")

    retry_seconds = document["retry_observation_seconds"]
    if isinstance(retry_seconds, bool) or not isinstance(retry_seconds, int):
        raise ControlledEvidenceError("manifest_retry_window_invalid")
    if retry_seconds < MIN_RETRY_OBSERVATION_SECONDS or retry_seconds > MAX_CONTROLLED_WINDOW_SECONDS:
        raise ControlledEvidenceError("manifest_retry_window_invalid")
    if not start < initial_cutoff < final_cutoff:
        raise ControlledEvidenceError("manifest_window_order_invalid")
    if (final_cutoff - start).total_seconds() > MAX_CONTROLLED_WINDOW_SECONDS:
        raise ControlledEvidenceError("manifest_window_too_wide")
    if (final_cutoff - initial_cutoff).total_seconds() < retry_seconds:
        raise ControlledEvidenceError("manifest_retry_window_too_short")

    raw_events = document["events"]
    if not isinstance(raw_events, dict):
        raise ControlledEvidenceError("manifest_events_invalid")
    _exact_keys(raw_events, set(CONTROLLED_SURFACES), reason="manifest_event_surfaces_invalid")
    events: dict[str, str] = {}
    for surface in CONTROLLED_SURFACES:
        event_id = str(raw_events[surface])
        if _EVENT_ID_RE.fullmatch(event_id) is None:
            raise ControlledEvidenceError("manifest_event_id_invalid")
        events[surface] = event_id
    if len(set(events.values())) != len(CONTROLLED_SURFACES):
        raise ControlledEvidenceError("manifest_event_ids_not_unique")

    raw_bindings = document["bindings"]
    if not isinstance(raw_bindings, dict):
        raise ControlledEvidenceError("manifest_bindings_invalid")
    _exact_keys(raw_bindings, set(CONTROLLED_SURFACES), reason="manifest_binding_surfaces_invalid")
    bindings: dict[str, str] = {}
    for surface in CONTROLLED_SURFACES:
        binding_digest = str(raw_bindings[surface])
        if _DIGEST_RE.fullmatch(binding_digest) is None:
            raise ControlledEvidenceError("manifest_binding_digest_invalid")
        bindings[surface] = binding_digest

    raw_topology = document["topology"]
    if not isinstance(raw_topology, dict):
        raise ControlledEvidenceError("manifest_topology_invalid")
    _exact_keys(
        raw_topology,
        {"failover_transaction_id", "initial_node", "replay_node"},
        reason="manifest_topology_fields_invalid",
    )
    failover_transaction_id = str(raw_topology["failover_transaction_id"])
    initial_node = str(raw_topology["initial_node"])
    replay_node = str(raw_topology["replay_node"])
    if _FAILOVER_TX_RE.fullmatch(failover_transaction_id) is None:
        raise ControlledEvidenceError("manifest_failover_transaction_invalid")
    if {initial_node, replay_node} != set(REQUIRED_NODES) or initial_node == replay_node:
        raise ControlledEvidenceError("manifest_failover_nodes_invalid")
    return ControlledManifest(
        test_run_id=test_run_id,
        release_sha=release_sha,
        start=start,
        initial_cutoff=initial_cutoff,
        final_cutoff=final_cutoff,
        retry_observation_seconds=retry_seconds,
        events=events,
        bindings=bindings,
        failover_transaction_id=failover_transaction_id,
        initial_node=initial_node,
        replay_node=replay_node,
    )


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


def read_controlled_manifest(source: str, expected_sha256: str) -> tuple[ControlledManifest, str]:
    """Read a race-safe root manifest, or explicit stdin, and verify raw hash."""

    if _MANIFEST_SHA_RE.fullmatch(expected_sha256) is None:
        raise ControlledEvidenceError("manifest_hash_invalid")
    if source == "-":
        try:
            raw = sys.stdin.buffer.read(MAX_MANIFEST_BYTES + 1)
        except OSError as exc:
            raise ControlledEvidenceError("manifest_stdin_unavailable") from exc
        if len(raw) > MAX_MANIFEST_BYTES:
            raise ControlledEvidenceError("manifest_size_invalid")
    else:
        path = Path(source)
        if not path.is_absolute():
            raise ControlledEvidenceError("manifest_path_not_absolute")
        try:
            before = os.lstat(path)
        except OSError as exc:
            raise ControlledEvidenceError("manifest_file_unavailable") from exc
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != 0
            or stat.S_IMODE(before.st_mode) != 0o600
            or before.st_nlink != 1
        ):
            raise ControlledEvidenceError("manifest_file_security_invalid")
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(path, flags)
        except OSError as exc:
            raise ControlledEvidenceError("manifest_file_unavailable") from exc
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
                raise ControlledEvidenceError("manifest_file_security_invalid")
            try:
                raw = _read_fd_limited(fd)
            except OSError as exc:
                raise ControlledEvidenceError("manifest_file_unavailable") from exc
        finally:
            os.close(fd)
    actual_sha256 = hashlib.sha256(raw).hexdigest()
    if not hmac.compare_digest(actual_sha256, expected_sha256):
        raise ControlledEvidenceError("manifest_hash_mismatch")
    return parse_controlled_manifest(raw), actual_sha256


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


def load_node_verification_keys(source: str) -> dict[str, Ed25519PublicKey]:
    raw = _read_root_owned_bytes(
        source,
        max_bytes=4096,
        unavailable_reason="node_verification_keys_unavailable",
        security_reason="node_verification_keys_security_invalid",
        size_reason="node_verification_keys_size_invalid",
    )
    values: dict[str, str] = {}
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise ControlledEvidenceError("node_verification_keys_invalid") from exc
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            raise ControlledEvidenceError("node_verification_keys_invalid")
        key, value = stripped.split("=", 1)
        if key in values:
            raise ControlledEvidenceError("node_verification_keys_invalid")
        values[key] = value.strip().strip("'\"")
    names = {node: f"CREDENTIAL_REKEY_{node.upper()}_VERIFY_KEY" for node in REQUIRED_NODES}
    if set(values) != set(names.values()):
        raise ControlledEvidenceError("node_verification_keys_invalid")
    keys: dict[str, Ed25519PublicKey] = {}
    raw_keys: list[bytes] = []
    try:
        for node, name in names.items():
            key_bytes = _decode_base64url(values[name], reason="node_verification_keys_invalid")
            if len(key_bytes) != 32:
                raise ControlledEvidenceError("node_verification_keys_invalid")
            raw_keys.append(key_bytes)
            keys[node] = Ed25519PublicKey.from_public_bytes(key_bytes)
    except (ValueError, TypeError) as exc:
        raise ControlledEvidenceError("node_verification_keys_invalid") from exc
    if hmac.compare_digest(raw_keys[0], raw_keys[1]):
        raise ControlledEvidenceError("node_verification_keys_not_distinct")
    return keys


def parse_failover_attestation(
    raw: bytes,
    *,
    manifest: ControlledManifest,
    manifest_sha256: str,
    verification_keys: Mapping[str, Ed25519PublicKey],
) -> FailoverAttestation:
    if not raw or len(raw) > MAX_ATTESTATION_BYTES:
        raise ControlledEvidenceError("failover_attestation_size_invalid")
    try:
        document = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_json_keys)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ControlledEvidenceError("failover_attestation_json_invalid") from exc
    if not isinstance(document, dict):
        raise ControlledEvidenceError("failover_attestation_shape_invalid")
    _exact_keys(
        document,
        {
            "schema",
            "phase",
            "transaction_id",
            "test_run_id",
            "manifest_sha256",
            "release_sha",
            "initial_node",
            "replay_node",
            "lb_ready_projection_sha256",
            "lb_pre_attestation_sha256",
            "lb_post_attestation_sha256",
            "lb_post_observed_at",
            "phase_started_at",
            "phase_proved_at",
            "minimum_drain_seconds",
            "public_ready_status",
            "node_proofs",
            "coordinator_signature",
        },
        reason="failover_attestation_fields_invalid",
    )
    phase = str(document["phase"])
    transaction_id = str(document["transaction_id"])
    test_run_id = str(document["test_run_id"])
    stored_manifest_sha = str(document["manifest_sha256"])
    release_sha = str(document["release_sha"])
    initial_node = str(document["initial_node"])
    replay_node = str(document["replay_node"])
    lb_digest = str(document["lb_ready_projection_sha256"])
    lb_pre_digest = str(document["lb_pre_attestation_sha256"])
    lb_post_digest = str(document["lb_post_attestation_sha256"])
    if document["schema"] != FAILOVER_SCHEMA or phase not in {"initial", "replay"}:
        raise ControlledEvidenceError("failover_attestation_schema_invalid")
    if (
        transaction_id != manifest.failover_transaction_id
        or _FAILOVER_TX_RE.fullmatch(transaction_id) is None
        or test_run_id != manifest.test_run_id
        or stored_manifest_sha != manifest_sha256
        or _MANIFEST_SHA_RE.fullmatch(stored_manifest_sha) is None
        or release_sha != manifest.release_sha
        or initial_node != manifest.initial_node
        or replay_node != manifest.replay_node
        or _DIGEST_RE.fullmatch(lb_digest) is None
        or _DIGEST_RE.fullmatch(lb_pre_digest) is None
        or _DIGEST_RE.fullmatch(lb_post_digest) is None
        or hmac.compare_digest(lb_pre_digest, lb_post_digest)
    ):
        raise ControlledEvidenceError("failover_attestation_binding_invalid")
    started_at = _parse_utc_timestamp(document["phase_started_at"], reason="failover_attestation_started_at_invalid")
    proved_at = _parse_utc_timestamp(document["phase_proved_at"], reason="failover_attestation_proved_at_invalid")
    lb_post_observed_at = _parse_utc_timestamp(
        document["lb_post_observed_at"],
        reason="failover_attestation_lb_post_timestamp_invalid",
    )
    minimum_drain = document["minimum_drain_seconds"]
    public_status = document["public_ready_status"]
    if (
        isinstance(minimum_drain, bool)
        or not isinstance(minimum_drain, int)
        or not 25 <= minimum_drain <= 300
        or isinstance(public_status, bool)
        or public_status != 200
        or not started_at < proved_at
        or (proved_at - started_at).total_seconds() < minimum_drain
        or not started_at < lb_post_observed_at <= proved_at
    ):
        raise ControlledEvidenceError("failover_attestation_transition_invalid")
    if phase == "initial":
        if proved_at > manifest.start or (manifest.start - proved_at).total_seconds() > 600:
            raise ControlledEvidenceError("failover_initial_window_invalid")
    elif started_at < manifest.initial_cutoff or proved_at >= manifest.final_cutoff:
        raise ControlledEvidenceError("failover_replay_window_invalid")

    raw_proofs = document["node_proofs"]
    if not isinstance(raw_proofs, dict) or set(raw_proofs) != set(REQUIRED_NODES):
        raise ControlledEvidenceError("failover_node_proofs_invalid")
    machine_ids: list[str] = []
    expected_state = {
        manifest.initial_node: (200, False) if phase == "initial" else (503, True),
        manifest.replay_node: (503, True) if phase == "initial" else (200, False),
    }
    for node in REQUIRED_NODES:
        proof = raw_proofs[node]
        if not isinstance(proof, dict):
            raise ControlledEvidenceError("failover_node_proof_invalid")
        _exact_keys(
            proof,
            {
                "node_id",
                "phase",
                "transaction_id",
                "release_sha",
                "direct_ready_status",
                "maintenance",
                "observed_at",
                "machine_id_sha256",
                "node_signature",
            },
            reason="failover_node_proof_fields_invalid",
        )
        status = proof["direct_ready_status"]
        maintenance = proof["maintenance"]
        machine_id = str(proof["machine_id_sha256"])
        observed_at = _parse_utc_timestamp(proof["observed_at"], reason="failover_node_proof_timestamp_invalid")
        if (
            proof["node_id"] != node
            or proof["phase"] != phase
            or proof["transaction_id"] != transaction_id
            or proof["release_sha"] != release_sha
            or isinstance(status, bool)
            or not isinstance(status, int)
            or not isinstance(maintenance, bool)
            or (status, maintenance) != expected_state[node]
            or not started_at <= observed_at <= proved_at
            or _DIGEST_RE.fullmatch(machine_id) is None
        ):
            raise ControlledEvidenceError("failover_node_proof_invalid")
        machine_ids.append(machine_id)
        signature = _decode_base64url(proof["node_signature"], reason="failover_node_signature_invalid")
        if len(signature) != 64:
            raise ControlledEvidenceError("failover_node_signature_invalid")
        body = {key: value for key, value in proof.items() if key != "node_signature"}
        try:
            verification_keys[node].verify(signature, _canonical_json(body))
        except (InvalidSignature, KeyError) as exc:
            raise ControlledEvidenceError("failover_node_signature_invalid") from exc
    if hmac.compare_digest(machine_ids[0], machine_ids[1]):
        raise ControlledEvidenceError("failover_node_identity_not_distinct")

    coordinator_signature = _decode_base64url(
        document["coordinator_signature"], reason="failover_coordinator_signature_invalid"
    )
    if len(coordinator_signature) != 64:
        raise ControlledEvidenceError("failover_coordinator_signature_invalid")
    body = {key: value for key, value in document.items() if key != "coordinator_signature"}
    try:
        verification_keys["node01"].verify(coordinator_signature, _canonical_json(body))
    except (InvalidSignature, KeyError) as exc:
        raise ControlledEvidenceError("failover_coordinator_signature_invalid") from exc
    return FailoverAttestation(
        phase=phase,
        transaction_id=transaction_id,
        test_run_id=test_run_id,
        manifest_sha256=stored_manifest_sha,
        release_sha=release_sha,
        initial_node=initial_node,
        replay_node=replay_node,
        lb_ready_projection_sha256=lb_digest,
        lb_pre_attestation_sha256=lb_pre_digest,
        lb_post_attestation_sha256=lb_post_digest,
        lb_post_observed_at=lb_post_observed_at,
        phase_started_at=started_at,
        phase_proved_at=proved_at,
        minimum_drain_seconds=minimum_drain,
    )


def read_failover_attestation(
    source: str,
    expected_sha256: str,
    *,
    manifest: ControlledManifest,
    manifest_sha256: str,
    verification_keys: Mapping[str, Ed25519PublicKey],
) -> tuple[FailoverAttestation, str]:
    if _MANIFEST_SHA_RE.fullmatch(expected_sha256) is None:
        raise ControlledEvidenceError("failover_attestation_hash_invalid")
    raw = _read_root_owned_bytes(
        source,
        max_bytes=MAX_ATTESTATION_BYTES,
        unavailable_reason="failover_attestation_unavailable",
        security_reason="failover_attestation_security_invalid",
        size_reason="failover_attestation_size_invalid",
    )
    actual_sha256 = hashlib.sha256(raw).hexdigest()
    if not hmac.compare_digest(actual_sha256, expected_sha256):
        raise ControlledEvidenceError("failover_attestation_hash_mismatch")
    return (
        parse_failover_attestation(
            raw,
            manifest=manifest,
            manifest_sha256=manifest_sha256,
            verification_keys=verification_keys,
        ),
        actual_sha256,
    )


def _iso_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _journal_base_args(*, start: datetime, cutoff: datetime, output: str) -> list[str]:
    args = ["journalctl"]
    for unit in _JOURNAL_UNITS:
        args.extend(["--unit", unit])
    args.extend(
        [
            "--since",
            _iso_utc(start),
            "--until",
            _iso_utc(cutoff),
            "--no-pager",
            "--output",
            output,
        ]
    )
    return args


def _run_command(args: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(args, check=False, capture_output=True, text=True)
    except OSError:
        # Callers convert this synthetic failure to a fixed, redacted reason.
        return subprocess.CompletedProcess(args=args, returncode=127, stdout="", stderr="")


def _read_release_sha(*, repo_dir: str, peer_host: str | None) -> str:
    def _on_node(command: list[str]) -> list[str]:
        if peer_host is None:
            return command
        return [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=8",
            "-o",
            "StrictHostKeyChecking=yes",
            f"root@{peer_host}",
            *command,
        ]

    result = _run_command(_on_node(["git", "-C", repo_dir, "rev-parse", "--verify", "HEAD"]))
    value = result.stdout.strip()
    if result.returncode != 0 or _RELEASE_SHA_RE.fullmatch(value) is None:
        raise ControlledEvidenceError("peer_release_read_failed" if peer_host else "local_release_read_failed")
    for command in (
        ["git", "-C", repo_dir, "diff", "--quiet", value, "--"],
        ["git", "-C", repo_dir, "diff", "--cached", "--quiet", value, "--"],
    ):
        clean = _run_command(_on_node(command))
        if clean.returncode != 0:
            raise ControlledEvidenceError("peer_release_dirty" if peer_host else "local_release_dirty")
    return value


def _read_controlled_journal(
    *,
    node: str,
    start: datetime,
    cutoff: datetime,
    peer_host: str | None,
) -> list[ControlledMarker]:
    command = _journal_base_args(start=start, cutoff=cutoff, output="json")
    if peer_host is not None:
        command = [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=8",
            "-o",
            "StrictHostKeyChecking=yes",
            f"root@{peer_host}",
            *command,
        ]
    result = _run_command(command)
    if result.returncode != 0:
        raise ControlledEvidenceError("peer_journal_read_failed" if peer_host else "local_journal_read_failed")
    markers: list[ControlledMarker] = []
    for raw_line in result.stdout.splitlines():
        try:
            record = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            raise ControlledEvidenceError(
                "peer_journal_format_invalid" if peer_host else "local_journal_format_invalid"
            ) from exc
        if not isinstance(record, dict):
            raise ControlledEvidenceError(
                "peer_journal_format_invalid" if peer_host else "local_journal_format_invalid"
            )
        message = record.get("MESSAGE")
        if not isinstance(message, str):
            continue
        marker = _CONTROLLED_MARKER_RE.search(message)
        if marker is None:
            continue
        raw_timestamp = record.get("__REALTIME_TIMESTAMP")
        try:
            occurred_at = datetime.fromtimestamp(int(str(raw_timestamp)) / 1_000_000, tz=UTC)
        except (TypeError, ValueError, OSError) as exc:
            raise ControlledEvidenceError(
                "peer_journal_timestamp_invalid" if peer_host else "local_journal_timestamp_invalid"
            ) from exc
        # Do not trust the journal command's filtering alone.  An out-of-window
        # record can never satisfy or poison this exact controlled run.
        if occurred_at < start or occurred_at > cutoff:
            continue
        surface, outcome, event_id = marker.groups()
        if outcome not in CONTROLLED_OUTCOMES:  # pragma: no cover - regex and allowlist are kept in lockstep
            continue
        markers.append(
            ControlledMarker(
                node=node,
                occurred_at=occurred_at,
                surface=surface,
                outcome=outcome,
                event_id=event_id,
            )
        )
    return markers


def evaluate_controlled_markers(
    manifest: ControlledManifest,
    markers: Iterable[ControlledMarker],
    *,
    replay_after: datetime | None = None,
) -> tuple[bool, dict[str, dict[str, Any]], list[str]]:
    """Evaluate exact event correlations without returning log messages or raw IDs."""

    marker_list = list(markers)
    expected_surface_by_event = {event_id: surface for surface, event_id in manifest.events.items()}
    summary: dict[str, dict[str, Any]] = {}
    reasons: list[str] = []
    for surface in CONTROLLED_SURFACES:
        event_id = manifest.events[surface]
        correlated = [item for item in marker_list if item.event_id == event_id]
        wrong_surface = [item for item in correlated if item.surface != surface]
        successes = [item for item in correlated if item.surface == surface and item.outcome == "provider_accepted"]
        forbidden = [item for item in correlated if item.outcome in FORBIDDEN_CONTROLLED_OUTCOMES]
        duplicate_suppressed = [
            item for item in correlated if item.surface == surface and item.outcome == "duplicate_suppressed"
        ]
        post_initial_replays = [
            item for item in duplicate_suppressed if replay_after is not None and item.occurred_at > replay_after
        ]
        auth = [
            item for item in correlated if item.surface == surface and item.outcome == "instagram_login_authenticated"
        ]
        nodes = sorted({item.node for item in successes})
        summary[surface] = {
            "provider_accepted": len(successes),
            "forbidden": len(forbidden),
            "duplicate_suppressed": len(duplicate_suppressed),
            "post_initial_duplicate_suppressed": len(post_initial_replays),
            "post_initial_replay_nodes": sorted({item.node for item in post_initial_replays}),
            "instagram_login_authenticated": len(auth),
            "nodes": nodes,
        }
        if len(successes) != 1:
            reasons.append(f"{surface}_provider_acceptance_count")
        elif successes[0].node != manifest.initial_node or successes[0].occurred_at > manifest.initial_cutoff:
            reasons.append(f"{surface}_initial_node_mismatch")
        if len(successes) > 1 and len(nodes) > 1:
            reasons.append(f"{surface}_cross_node_duplicate")
        if forbidden:
            reasons.append(f"{surface}_forbidden_outcome")
        if wrong_surface:
            reasons.append(f"{surface}_surface_mismatch")
        if surface.startswith("instagram_") and len(auth) != 1:
            reasons.append(f"{surface}_dedicated_auth_count")
        elif surface.startswith("instagram_") and (
            auth[0].node != manifest.initial_node or auth[0].occurred_at > manifest.initial_cutoff
        ):
            reasons.append(f"{surface}_dedicated_auth_node_mismatch")
        if replay_after is not None:
            if len(post_initial_replays) != 1:
                reasons.append(f"{surface}_post_initial_replay_count")
            elif post_initial_replays[0].node != manifest.replay_node:
                reasons.append(f"{surface}_replay_node_mismatch")

    # A manifest event reused under another surface is already rejected during
    # parsing; this catches any journal marker that tries to reclassify one.
    for marker in marker_list:
        expected = expected_surface_by_event.get(marker.event_id)
        if expected is not None and marker.surface != expected:
            mismatch = f"{expected}_surface_mismatch"
            if mismatch not in reasons:
                reasons.append(mismatch)
    return not reasons, summary, reasons


def evaluate_controlled_attempt_documents(
    manifest: ControlledManifest,
    documents: Mapping[str, Mapping[str, Any]],
) -> tuple[bool, dict[str, dict[str, Any]], list[str]]:
    """Prove one first-attempt provider acceptance in the shared send ledger."""

    summary: dict[str, dict[str, Any]] = {}
    reasons: list[str] = []
    for surface in CONTROLLED_SURFACES:
        event_id = manifest.events[surface]
        document = documents.get(event_id)
        raw = document if isinstance(document, Mapping) else {}
        status = str(raw.get("status") or "")
        stored_surface = str(raw.get("surface") or "")
        sequence = int(raw.get("attempt_sequence") or 0)
        provider_digest = str(raw.get("provider_message_id_sha256") or "")
        binding_digest = str(raw.get("binding_id_sha256") or "")
        binding_matches = hmac.compare_digest(binding_digest, manifest.bindings[surface])
        valid = (
            str(raw.get("event_id") or "") == event_id
            and stored_surface == surface
            and status == "accepted"
            and sequence == 1
            and _DIGEST_RE.fullmatch(provider_digest) is not None
            and binding_matches
        )
        summary[surface] = {
            "status": status
            if status in {"accepted", "needs_owner_action", "definitive_failure", "sending"}
            else "invalid",
            "attempt_sequence": sequence,
            "provider_id_hash_present": _DIGEST_RE.fullmatch(provider_digest) is not None,
            "binding_hash_matches_expected": binding_matches,
        }
        if not binding_matches:
            reasons.append(f"{surface}_binding_mismatch")
        elif not valid:
            reasons.append(f"{surface}_shared_attempt_invalid")
    return not reasons, summary, reasons


def _read_shared_outbound_attempts(manifest: ControlledManifest) -> dict[str, Mapping[str, Any]]:
    try:
        from utils.utils import get_firestore_db

        db = get_firestore_db()
    except Exception as exc:
        raise ControlledEvidenceError("shared_attempt_store_unavailable") from exc
    if db is None:
        raise ControlledEvidenceError("shared_attempt_store_unavailable")
    collection = db.collection("artifacts").document("linas-ai-bot-backend").collection("meta_outbound_attempts")
    documents: dict[str, Mapping[str, Any]] = {}
    try:
        for event_id in manifest.events.values():
            snapshot = collection.document(event_id).get()
            data = snapshot.to_dict() if snapshot.exists else None
            documents[event_id] = data if isinstance(data, Mapping) else {}
    except Exception as exc:
        raise ControlledEvidenceError("shared_attempt_store_read_failed") from exc
    return documents


def _phase_cutoff(manifest: ControlledManifest, *, phase: str, now: datetime) -> datetime:
    cutoff = manifest.initial_cutoff if phase == "initial" else manifest.final_cutoff
    if now < cutoff:
        raise ControlledEvidenceError("controlled_check_before_cutoff")
    if phase == "initial" and now >= manifest.final_cutoff:
        raise ControlledEvidenceError("controlled_initial_check_too_late")
    if (now - cutoff).total_seconds() > MAX_CHECK_DELAY_SECONDS:
        raise ControlledEvidenceError("controlled_manifest_stale")
    return cutoff


def _run_controlled_gate(args: argparse.Namespace) -> int:
    try:
        manifest, manifest_sha = read_controlled_manifest(args.controlled_manifest, args.manifest_sha256)
        if args.expected_release_sha != manifest.release_sha:
            raise ControlledEvidenceError("workflow_release_manifest_mismatch")
        now = datetime.now(UTC)
        cutoff = _phase_cutoff(manifest, phase=args.phase, now=now)
        local_release = _read_release_sha(repo_dir=args.repo_dir, peer_host=None)
        peer_release = _read_release_sha(repo_dir=args.repo_dir, peer_host=args.peer_host)
        if local_release != manifest.release_sha:
            raise ControlledEvidenceError("local_release_mismatch")
        if peer_release != manifest.release_sha:
            raise ControlledEvidenceError("peer_release_mismatch")
        verification_keys = load_node_verification_keys(args.node_verification_keys_file)
        initial_attestation, initial_attestation_sha = read_failover_attestation(
            args.initial_attestation,
            args.initial_attestation_sha256,
            manifest=manifest,
            manifest_sha256=manifest_sha,
            verification_keys=verification_keys,
        )
        if initial_attestation.phase != "initial":
            raise ControlledEvidenceError("failover_initial_phase_invalid")
        replay_attestation: FailoverAttestation | None = None
        replay_attestation_sha: str | None = None
        if args.phase == "final":
            replay_attestation, replay_attestation_sha = read_failover_attestation(
                args.replay_attestation,
                args.replay_attestation_sha256,
                manifest=manifest,
                manifest_sha256=manifest_sha,
                verification_keys=verification_keys,
            )
            if replay_attestation.phase != "replay":
                raise ControlledEvidenceError("failover_replay_phase_invalid")
            if replay_attestation.lb_ready_projection_sha256 != initial_attestation.lb_ready_projection_sha256:
                raise ControlledEvidenceError("failover_lb_projection_changed")
        markers = _read_controlled_journal(
            node="node01",
            start=manifest.start,
            cutoff=cutoff,
            peer_host=None,
        )
        markers.extend(
            _read_controlled_journal(
                node="node02",
                start=manifest.start,
                cutoff=cutoff,
                peer_host=args.peer_host,
            )
        )
        passed, summary, reasons = evaluate_controlled_markers(
            manifest,
            markers,
            replay_after=replay_attestation.phase_proved_at if replay_attestation is not None else None,
        )
        attempts = _read_shared_outbound_attempts(manifest)
        attempts_passed, attempt_summary, attempt_reasons = evaluate_controlled_attempt_documents(
            manifest,
            attempts,
        )
        passed = passed and attempts_passed
        reasons.extend(attempt_reasons)
    except ControlledEvidenceError as exc:
        print(f"[controlled-evidence] GATE_FAILED reason={exc}")
        return 2

    print(
        f"[controlled-evidence] phase={args.phase} test_run_id={manifest.test_run_id} "
        f"manifest_sha256={manifest_sha} release_sha={manifest.release_sha} "
        f"initial_node={manifest.initial_node} replay_node={manifest.replay_node} "
        f"initial_attestation_sha256={initial_attestation_sha}"
    )
    if replay_attestation_sha is not None:
        print(f"[controlled-evidence] replay_attestation_sha256={replay_attestation_sha}")
    for surface in CONTROLLED_SURFACES:
        item = summary[surface]
        nodes = ",".join(item["nodes"]) or "none"
        replay_nodes = ",".join(item["post_initial_replay_nodes"]) or "none"
        print(
            f"[controlled-evidence] surface={surface} provider_accepted={item['provider_accepted']} "
            f"forbidden={item['forbidden']} duplicate_suppressed={item['duplicate_suppressed']} "
            f"dedicated_auth={item['instagram_login_authenticated']} "
            f"nodes={nodes} replay_nodes={replay_nodes}"
        )
        attempt = attempt_summary[surface]
        print(
            f"[controlled-evidence] surface={surface} shared_status={attempt['status']} "
            f"shared_attempt_sequence={attempt['attempt_sequence']} "
            f"shared_provider_hash={str(attempt['provider_id_hash_present']).lower()}"
        )
    if not passed:
        print(f"[controlled-evidence] GATE_FAILED reasons={','.join(sorted(set(reasons)))}")
        return 2
    print(f"[controlled-evidence] GATE_PASSED phase={args.phase}")
    return 0


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--require-evidence",
        action="store_true",
        help="Require coarse, uncorrelated diagnostic coverage (not valid as final controlled-test proof).",
    )
    parser.add_argument(
        "--window-minutes",
        type=int,
        default=30,
        help="Only inspect journal entries from this many recent minutes in diagnostic mode (default: 30).",
    )
    parser.add_argument(
        "--include-file-tails",
        action="store_true",
        help="Also inspect undated log-file tails in diagnostic mode; forbidden with coarse evidence requirements.",
    )
    parser.add_argument(
        "--include-ha-peer",
        action="store_true",
        help="Aggregate the diagnostic window from the required HA peer.",
    )
    parser.add_argument(
        "--peer-host",
        default="10.106.0.4",
        help="Internal HA peer hostname or address (default: 10.106.0.4).",
    )
    parser.add_argument(
        "--controlled-manifest",
        help="Root-owned 0600 manifest path, or '-' to read the manifest from stdin.",
    )
    parser.add_argument("--manifest-sha256", help="Expected SHA-256 of the exact controlled manifest bytes.")
    parser.add_argument("--initial-attestation", help="Root-owned initial-routing attestation path.")
    parser.add_argument("--initial-attestation-sha256", help="Expected SHA-256 of the initial attestation.")
    parser.add_argument("--replay-attestation", help="Root-owned post-failover routing attestation path.")
    parser.add_argument("--replay-attestation-sha256", help="Expected SHA-256 of the replay attestation.")
    parser.add_argument(
        "--node-verification-keys-file",
        default=NODE_VERIFICATION_KEYS_FILE,
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--phase", choices=("initial", "final"), help="Controlled proof phase.")
    parser.add_argument("--expected-release-sha", help="Exact deployed release required by the workflow.")
    parser.add_argument("--repo-dir", default="/opt/linasbot", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.window_minutes < 1 or args.window_minutes > 10_080:
        parser.error("--window-minutes must be between 1 and 10080")
    if args.require_evidence and args.window_minutes > 60:
        parser.error("coarse evidence requires --window-minutes between 1 and 60")
    if args.require_evidence and args.include_file_tails:
        parser.error("--include-file-tails cannot be used as bounded coarse evidence")
    if _PEER_RE.fullmatch(str(args.peer_host)) is None:
        parser.error("--peer-host is invalid")
    controlled_args = (
        args.controlled_manifest,
        args.manifest_sha256,
        args.phase,
        args.expected_release_sha,
        args.initial_attestation,
        args.initial_attestation_sha256,
    )
    if args.controlled_manifest:
        if not all(controlled_args):
            parser.error("controlled mode requires manifest, failover attestation, hashes, phase, and release SHA")
        for value, label in (
            (args.manifest_sha256, "--manifest-sha256"),
            (args.initial_attestation_sha256, "--initial-attestation-sha256"),
        ):
            if _MANIFEST_SHA_RE.fullmatch(str(value)) is None:
                parser.error(f"{label} must be 64 lowercase hexadecimal characters")
        if _RELEASE_SHA_RE.fullmatch(str(args.expected_release_sha)) is None:
            parser.error("--expected-release-sha must be 40 lowercase hexadecimal characters")
        if args.phase == "final":
            if not args.replay_attestation or _MANIFEST_SHA_RE.fullmatch(str(args.replay_attestation_sha256)) is None:
                parser.error("final controlled mode requires replay attestation and exact SHA-256")
        elif args.replay_attestation or args.replay_attestation_sha256:
            parser.error("replay attestation is valid only for the final controlled phase")
        if args.require_evidence or args.include_file_tails or args.include_ha_peer:
            parser.error("controlled mode is separate from diagnostic evidence options")
    elif any((*controlled_args[1:], args.replay_attestation, args.replay_attestation_sha256)):
        parser.error("--controlled-manifest is required with controlled-mode options")
    return args


def _diagnostic_journal_command(*, window_minutes: int, peer_host: str | None) -> list[str]:
    args = ["journalctl"]
    for unit in _JOURNAL_UNITS:
        args.extend(["--unit", unit])
    args.extend(["--since", f"{window_minutes} minutes ago", "--no-pager", "--output", "cat"])
    if peer_host is None:
        return args
    return [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=8",
        "-o",
        "StrictHostKeyChecking=yes",
        f"root@{peer_host}",
        *args,
    ]


def _run_diagnostic(args: argparse.Namespace) -> int:
    journal = _run_command(_diagnostic_journal_command(window_minutes=args.window_minutes, peer_host=None))
    lines = journal.stdout.splitlines()
    peer_journal_returncode: int | None = None
    peer_line_count = 0
    if args.include_ha_peer:
        peer_journal = _run_command(
            _diagnostic_journal_command(window_minutes=args.window_minutes, peer_host=args.peer_host)
        )
        peer_journal_returncode = int(peer_journal.returncode)
        peer_lines = peer_journal.stdout.splitlines()
        peer_line_count = len(peer_lines)
        lines.extend(peer_lines)
    if args.include_file_tails:
        for pattern in (
            "/var/log/linasbot.log",
            "/var/log/linasbot.error.log",
            "/var/log/nginx/access.log",
            "/var/log/nginx/error.log",
            "/opt/linasbot/logs/*",
        ):
            for raw in glob.glob(pattern):
                path = Path(raw)
                if path.is_file():
                    lines.extend(_read_tail(path))

    counts = scan_evidence(lines)
    print(
        f"[comment-probe] journal_exit={journal.returncode} window_minutes={args.window_minutes} "
        f"file_tails={str(args.include_file_tails).lower()} ha_peer={str(args.include_ha_peer).lower()} "
        f"peer_journal_exit={peer_journal_returncode} peer_scanned_lines={peer_line_count} "
        f"scanned_lines={len(lines)}"
    )
    for name in sorted(PATTERNS):
        print(f"[comment-probe] {name}={counts[name]}")

    status_reasons: Counter[str] = Counter()
    for line in lines:
        match = re.search(
            r"\[meta-comment\] event_processing_completed channel=(\w+) status=(\w+) reason=([^\s]+)",
            line,
        )
        if match:
            status_reasons[f"{match.group(1)}:{match.group(2)}:{match.group(3)}"] += 1
        drop = re.search(
            r"\[meta-comment\] events_dropped object=(\w+) raw=(\d+) resolved=0 bindings=(\d+) reasons=(\{.*\})",
            line,
        )
        if drop:
            print(
                f"[comment-probe] drop object={drop.group(1)} raw={drop.group(2)} "
                f"bindings={drop.group(3)} reasons={drop.group(4)}"
            )
        ig = re.search(
            r"\[instagram-login\] webhook_authenticated object=(\w+) parsed=(\d+) "
            r"accepted=(\d+) duplicates=(\d+) comments=(\d+)",
            line,
        )
        if ig and int(ig.group(5)) > 0:
            print(
                f"[comment-probe] ig_login_comments object={ig.group(1)} "
                f"parsed={ig.group(2)} accepted={ig.group(3)} comments={ig.group(5)}"
            )
        mc = re.search(
            r"\[meta-comment\] webhook_authenticated object=(\w+) raw=(\d+) "
            r"parsed=(\d+) accepted=(\d+) duplicates=(\d+)",
            line,
        )
        if mc:
            print(
                f"[comment-probe] meta_comment_auth object={mc.group(1)} raw={mc.group(2)} "
                f"parsed={mc.group(3)} accepted={mc.group(4)}"
            )

    print(f"[comment-probe] completed_status_variants={len(status_reasons)}")
    for key, count in sorted(status_reasons.items()):
        print(f"[comment-probe] completed {key} occurrences={count}")
    if args.require_evidence:
        if journal.returncode != 0 or (args.include_ha_peer and peer_journal_returncode != 0):
            print("[comment-probe] COARSE_EVIDENCE_FAILED reason=journal_read_failed")
            return 2
        missing = missing_required_evidence(counts)
        for label, counter_name in REQUIRED_EVIDENCE.items():
            state = "PASS" if counts[counter_name] > 0 else "FAIL"
            print(f"[comment-probe] coarse {label}={state} count={counts[counter_name]}")
        if missing:
            print(f"[comment-probe] COARSE_EVIDENCE_FAILED missing={','.join(missing)}")
            return 2
        print("[comment-probe] COARSE_EVIDENCE_PASSED")
    print("[comment-probe] SUCCESS")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.controlled_manifest:
        return _run_controlled_gate(args)
    return _run_diagnostic(args)


if __name__ == "__main__":
    raise SystemExit(main())
