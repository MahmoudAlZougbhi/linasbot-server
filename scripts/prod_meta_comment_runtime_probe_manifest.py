"""Parse and verify closed-schema controlled manifests and failover attestations."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import stat
import sys
from collections.abc import Mapping
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from scripts.prod_meta_comment_runtime_probe_types import (
    _DIGEST_RE,
    _EVENT_ID_RE,
    _FAILOVER_TX_RE,
    _MANIFEST_SHA_RE,
    _RELEASE_SHA_RE,
    _RUN_ID_RE,
    CONTROLLED_SCHEMA,
    CONTROLLED_SURFACES,
    FAILOVER_SCHEMA,
    MAX_ATTESTATION_BYTES,
    MAX_CONTROLLED_WINDOW_SECONDS,
    MAX_MANIFEST_BYTES,
    MIN_RETRY_OBSERVATION_SECONDS,
    REQUIRED_NODES,
    ControlledEvidenceError,
    ControlledManifest,
    FailoverAttestation,
    _canonical_json,
    _decode_base64url,
    _exact_keys,
    _parse_utc_timestamp,
    _read_fd_limited,
    _read_root_owned_bytes,
    _reject_duplicate_json_keys,
)


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
