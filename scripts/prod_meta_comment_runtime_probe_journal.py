"""Journal collection and correlated controlled-evidence evaluation."""

from __future__ import annotations

import hmac
import json
import subprocess
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.prod_meta_comment_runtime_probe_types import (
    _CONTROLLED_MARKER_RE,
    _DIGEST_RE,
    _JOURNAL_UNITS,
    _RELEASE_SHA_RE,
    CONTROLLED_OUTCOMES,
    CONTROLLED_SURFACES,
    FORBIDDEN_CONTROLLED_OUTCOMES,
    MAX_CHECK_DELAY_SECONDS,
    ControlledEvidenceError,
    ControlledManifest,
    ControlledMarker,
    _iso_utc,
)


def _read_tail(path: Path, *, max_bytes: int = 4_000_000) -> list[str]:
    try:
        with path.open("rb") as handle:
            handle.seek(0, 2)
            size = handle.tell()
            handle.seek(max(0, size - max_bytes))
            return handle.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return []


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


def _invoke_run_command(args: list[str]) -> subprocess.CompletedProcess[str]:
    from scripts.prod_meta_comment_runtime_probe import _run_command as run_command

    return run_command(args)


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

    result = _invoke_run_command(_on_node(["git", "-C", repo_dir, "rev-parse", "--verify", "HEAD"]))
    value = result.stdout.strip()
    if result.returncode != 0 or _RELEASE_SHA_RE.fullmatch(value) is None:
        raise ControlledEvidenceError("peer_release_read_failed" if peer_host else "local_release_read_failed")
    for command in (
        ["git", "-C", repo_dir, "diff", "--quiet", value, "--"],
        ["git", "-C", repo_dir, "diff", "--cached", "--quiet", value, "--"],
    ):
        clean = _invoke_run_command(_on_node(command))
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
    result = _invoke_run_command(command)
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
