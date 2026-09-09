"""Production Meta comment runtime probe attestation and release tests."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import serialization

import scripts.prod_meta_comment_runtime_probe as probe
from tests.prod_meta_comment_runtime_probe_support import (
    BINDINGS,
    EVENTS,
    NODE_KEYS,
    RELEASE_SHA,
    _attestation_bytes,
    _b64,
    _complete_attempt_documents,
    _complete_controlled_markers,
    _controlled_manifest,
    _journal_json,
    _manifest_bytes,
    _marker_message,
    _verification_keys,
)

pytest_plugins = ('tests.prod_meta_comment_runtime_probe_support',)

def test_manifest_requires_exact_four_distinct_event_ids() -> None:
    duplicate = dict(EVENTS)
    duplicate["instagram_comment"] = duplicate["instagram_dm"]
    with pytest.raises(probe.ControlledEvidenceError, match="manifest_event_ids_not_unique"):
        _controlled_manifest(events=duplicate)

    missing = dict(EVENTS)
    missing.pop("facebook_comment")
    with pytest.raises(probe.ControlledEvidenceError, match="manifest_event_surfaces_invalid"):
        _controlled_manifest(events=missing)

    wrong_bindings = dict(BINDINGS)
    wrong_bindings["instagram_comment"] = "not-a-digest"
    with pytest.raises(probe.ControlledEvidenceError, match="manifest_binding_digest_invalid"):
        _controlled_manifest(bindings=wrong_bindings)

    missing_bindings = dict(BINDINGS)
    missing_bindings.pop("facebook_dm")
    with pytest.raises(probe.ControlledEvidenceError, match="manifest_binding_surfaces_invalid"):
        _controlled_manifest(bindings=missing_bindings)


def test_signed_failover_attestations_bind_both_distinct_nodes_and_phase_windows() -> None:
    raw_manifest = _manifest_bytes()
    manifest = probe.parse_controlled_manifest(raw_manifest)
    manifest_sha = hashlib.sha256(raw_manifest).hexdigest()

    initial = probe.parse_failover_attestation(
        _attestation_bytes(manifest, manifest_sha, phase="initial"),
        manifest=manifest,
        manifest_sha256=manifest_sha,
        verification_keys=_verification_keys(),
    )
    replay = probe.parse_failover_attestation(
        _attestation_bytes(manifest, manifest_sha, phase="replay"),
        manifest=manifest,
        manifest_sha256=manifest_sha,
        verification_keys=_verification_keys(),
    )

    assert initial.phase == "initial"
    assert replay.phase == "replay"
    assert initial.lb_ready_projection_sha256 == replay.lb_ready_projection_sha256
    assert initial.lb_pre_attestation_sha256 != initial.lb_post_attestation_sha256
    assert initial.phase_started_at < initial.lb_post_observed_at <= initial.phase_proved_at
    assert replay.phase_proved_at > manifest.initial_cutoff


def test_failover_attestation_requires_distinct_in_phase_lb_observations() -> None:
    raw_manifest = _manifest_bytes()
    manifest = probe.parse_controlled_manifest(raw_manifest)
    manifest_sha = hashlib.sha256(raw_manifest).hexdigest()

    same_artifact = json.loads(_attestation_bytes(manifest, manifest_sha, phase="replay"))
    same_artifact["lb_post_attestation_sha256"] = same_artifact["lb_pre_attestation_sha256"]
    with pytest.raises(probe.ControlledEvidenceError, match="failover_attestation_binding_invalid"):
        probe.parse_failover_attestation(
            json.dumps(same_artifact, separators=(",", ":"), sort_keys=True).encode(),
            manifest=manifest,
            manifest_sha256=manifest_sha,
            verification_keys=_verification_keys(),
        )

    stale_post = json.loads(_attestation_bytes(manifest, manifest_sha, phase="replay"))
    stale_post["lb_post_observed_at"] = manifest.start.isoformat().replace("+00:00", "Z")
    with pytest.raises(probe.ControlledEvidenceError, match="failover_attestation_transition_invalid"):
        probe.parse_failover_attestation(
            json.dumps(stale_post, separators=(",", ":"), sort_keys=True).encode(),
            manifest=manifest,
            manifest_sha256=manifest_sha,
            verification_keys=_verification_keys(),
        )

    equal_transition = json.loads(_attestation_bytes(manifest, manifest_sha, phase="replay"))
    equal_transition["lb_post_observed_at"] = equal_transition["phase_started_at"]
    with pytest.raises(probe.ControlledEvidenceError, match="failover_attestation_transition_invalid"):
        probe.parse_failover_attestation(
            json.dumps(equal_transition, separators=(",", ":"), sort_keys=True).encode(),
            manifest=manifest,
            manifest_sha256=manifest_sha,
            verification_keys=_verification_keys(),
        )


def test_failover_attestation_rejects_same_host_forgery_and_signature_tamper() -> None:
    raw_manifest = _manifest_bytes()
    manifest = probe.parse_controlled_manifest(raw_manifest)
    manifest_sha = hashlib.sha256(raw_manifest).hexdigest()
    decoded = json.loads(_attestation_bytes(manifest, manifest_sha, phase="replay"))
    decoded["node_proofs"]["node02"]["machine_id_sha256"] = "1" * 64
    tampered = json.dumps(decoded, separators=(",", ":"), sort_keys=True).encode()

    with pytest.raises(probe.ControlledEvidenceError, match="failover_node_signature_invalid"):
        probe.parse_failover_attestation(
            tampered,
            manifest=manifest,
            manifest_sha256=manifest_sha,
            verification_keys=_verification_keys(),
        )


def test_node_verification_key_file_requires_two_distinct_root_only_keys(tmp_path, monkeypatch) -> None:
    path = tmp_path / "node-verification-keys.env"
    values = []
    for node in probe.REQUIRED_NODES:
        raw = (
            NODE_KEYS[node]
            .public_key()
            .public_bytes(
                serialization.Encoding.Raw,
                serialization.PublicFormat.Raw,
            )
        )
        values.append(f"CREDENTIAL_REKEY_{node.upper()}_VERIFY_KEY={_b64(raw)}")
    path.write_text("\n".join(values) + "\n", encoding="utf-8")
    path.chmod(0o600)
    real_lstat = os.lstat(path)
    real_fstat = os.stat(path)

    def _owned(value):
        return SimpleNamespace(
            st_mode=value.st_mode,
            st_uid=0,
            st_nlink=1,
            st_dev=value.st_dev,
            st_ino=value.st_ino,
        )

    monkeypatch.setattr(probe.os, "lstat", lambda _path: _owned(real_lstat))
    monkeypatch.setattr(probe.os, "fstat", lambda _fd: _owned(real_fstat))
    assert set(probe.load_node_verification_keys(str(path))) == set(probe.REQUIRED_NODES)


def test_root_manifest_security_requires_owner_only_regular_nonlinked_file(tmp_path, monkeypatch) -> None:
    raw = _manifest_bytes()
    path = tmp_path / "controlled.json"
    path.write_bytes(raw)
    path.chmod(0o600)
    real_lstat = os.lstat(path)
    real_fstat = os.stat(path)

    def _owned(value):
        return SimpleNamespace(
            st_mode=value.st_mode,
            st_uid=0,
            st_nlink=1,
            st_dev=value.st_dev,
            st_ino=value.st_ino,
        )

    monkeypatch.setattr(probe.os, "lstat", lambda _path: _owned(real_lstat))
    monkeypatch.setattr(probe.os, "fstat", lambda _fd: _owned(real_fstat))
    manifest, digest = probe.read_controlled_manifest(str(path), hashlib.sha256(raw).hexdigest())
    assert manifest.release_sha == RELEASE_SHA
    assert digest == hashlib.sha256(raw).hexdigest()

    insecure = _owned(real_lstat)
    insecure.st_mode = stat.S_IFREG | 0o640
    monkeypatch.setattr(probe.os, "lstat", lambda _path: insecure)
    with pytest.raises(probe.ControlledEvidenceError, match="manifest_file_security_invalid"):
        probe.read_controlled_manifest(str(path), hashlib.sha256(raw).hexdigest())


def test_stale_journal_marker_cannot_satisfy_controlled_window(monkeypatch) -> None:
    manifest = _controlled_manifest()
    stale = manifest.start - timedelta(seconds=1)
    message = f"[meta-evidence-v2] event surface=facebook_dm outcome=provider_accepted event_id={EVENTS['facebook_dm']}"
    monkeypatch.setattr(
        probe,
        "_run_command",
        lambda _args: SimpleNamespace(returncode=0, stdout=_journal_json(message, stale)),
    )

    markers = probe._read_controlled_journal(
        node="node01",
        start=manifest.start,
        cutoff=manifest.initial_cutoff,
        peer_host=None,
    )

    assert markers == []


def test_phase_check_rejects_stale_manifest() -> None:
    manifest = _controlled_manifest()
    with pytest.raises(probe.ControlledEvidenceError, match="controlled_manifest_stale"):
        probe._phase_cutoff(
            manifest,
            phase="final",
            now=manifest.final_cutoff + timedelta(seconds=probe.MAX_CHECK_DELAY_SECONDS + 1),
        )


def test_initial_phase_must_run_before_post_retry_final_cutoff() -> None:
    manifest = _controlled_manifest()
    with pytest.raises(probe.ControlledEvidenceError, match="controlled_initial_check_too_late"):
        probe._phase_cutoff(manifest, phase="initial", now=manifest.final_cutoff)


def test_final_phase_catches_duplicate_after_initial_retry_cutoff(monkeypatch) -> None:
    manifest = _controlled_manifest()
    initial_markers = _complete_controlled_markers()
    duplicate = probe.ControlledMarker(
        node="node01",
        occurred_at=manifest.initial_cutoff + timedelta(minutes=1),
        surface="instagram_dm",
        outcome="provider_accepted",
        event_id=EVENTS["instagram_dm"],
    )
    lines = [_journal_json(_marker_message(item), item.occurred_at) for item in [*initial_markers, duplicate]]
    monkeypatch.setattr(
        probe,
        "_run_command",
        lambda _args: SimpleNamespace(returncode=0, stdout="\n".join(lines)),
    )

    initial = probe._read_controlled_journal(
        node="node01",
        start=manifest.start,
        cutoff=manifest.initial_cutoff,
        peer_host=None,
    )
    final = probe._read_controlled_journal(
        node="node01",
        start=manifest.start,
        cutoff=manifest.final_cutoff,
        peer_host=None,
    )

    assert probe.evaluate_controlled_markers(manifest, initial)[0] is True
    passed, _summary, reasons = probe.evaluate_controlled_markers(manifest, final)
    assert passed is False
    assert "instagram_dm_provider_acceptance_count" in reasons


def test_controlled_gate_checks_exact_release_and_both_nodes(monkeypatch) -> None:
    now = datetime.now(UTC)
    manifest = _controlled_manifest(
        start=now - timedelta(minutes=8),
        initial_cutoff=now - timedelta(seconds=1),
        final_cutoff=now + timedelta(minutes=5),
    )
    release_calls: list[str | None] = []
    journal_calls: list[str] = []
    current_markers = [
        probe.ControlledMarker(
            node=item.node,
            occurred_at=manifest.start + timedelta(seconds=30),
            surface=item.surface,
            outcome=item.outcome,
            event_id=item.event_id,
        )
        for item in _complete_controlled_markers()
    ]
    by_node = {
        "node01": [item for item in current_markers if item.node == "node01"],
        "node02": [item for item in current_markers if item.node == "node02"],
    }
    monkeypatch.setattr(
        probe,
        "read_controlled_manifest",
        lambda *_args: (manifest, "c" * 64),
    )

    def _release(*, repo_dir: str, peer_host: str | None) -> str:
        assert repo_dir == "/opt/linasbot"
        release_calls.append(peer_host)
        return RELEASE_SHA

    def _journal(*, node: str, start, cutoff, peer_host):
        journal_calls.append(node)
        return by_node[node]

    monkeypatch.setattr(probe, "_read_release_sha", _release)
    monkeypatch.setattr(probe, "_read_controlled_journal", _journal)
    monkeypatch.setattr(probe, "_read_shared_outbound_attempts", lambda _manifest: _complete_attempt_documents())
    monkeypatch.setattr(probe, "load_node_verification_keys", lambda _path: _verification_keys())
    initial = probe.FailoverAttestation(
        phase="initial",
        transaction_id=manifest.failover_transaction_id,
        test_run_id=manifest.test_run_id,
        manifest_sha256="c" * 64,
        release_sha=manifest.release_sha,
        initial_node=manifest.initial_node,
        replay_node=manifest.replay_node,
        lb_ready_projection_sha256="d" * 64,
        lb_pre_attestation_sha256="a" * 64,
        lb_post_attestation_sha256="b" * 64,
        lb_post_observed_at=manifest.start - timedelta(seconds=30),
        phase_started_at=manifest.start - timedelta(seconds=60),
        phase_proved_at=manifest.start - timedelta(seconds=30),
        minimum_drain_seconds=25,
    )
    monkeypatch.setattr(
        probe,
        "read_failover_attestation",
        lambda *_args, **_kwargs: (initial, "e" * 64),
    )
    args = SimpleNamespace(
        controlled_manifest="/var/lib/linasbot/meta-evidence/controlled.json",
        manifest_sha256="c" * 64,
        expected_release_sha=RELEASE_SHA,
        phase="initial",
        repo_dir="/opt/linasbot",
        peer_host="10.106.0.4",
        node_verification_keys_file="/var/lib/linasbot/meta-ha/node-verification-keys.env",
        initial_attestation="/var/lib/linasbot/meta-evidence/failover/initial.json",
        initial_attestation_sha256="e" * 64,
        replay_attestation=None,
        replay_attestation_sha256=None,
    )

    assert probe._run_controlled_gate(args) == 0
    assert release_calls == [None, "10.106.0.4"]
    assert journal_calls == ["node01", "node02"]

    args.expected_release_sha = "d" * 40
    assert probe._run_controlled_gate(args) == 2


def test_release_check_rejects_tracked_drift_on_either_node(monkeypatch) -> None:
    clean_results = iter(
        [
            SimpleNamespace(returncode=0, stdout=RELEASE_SHA),
            SimpleNamespace(returncode=0, stdout=""),
            SimpleNamespace(returncode=0, stdout=""),
        ]
    )
    commands: list[list[str]] = []

    def _clean(command):
        commands.append(command)
        return next(clean_results)

    monkeypatch.setattr(probe, "_run_command", _clean)
    assert probe._read_release_sha(repo_dir="/opt/linasbot", peer_host="10.106.0.4") == RELEASE_SHA
    assert all(command[0] == "ssh" for command in commands)

    dirty_results = iter(
        [
            SimpleNamespace(returncode=0, stdout=RELEASE_SHA),
            SimpleNamespace(returncode=1, stdout=""),
        ]
    )
    monkeypatch.setattr(probe, "_run_command", lambda _command: next(dirty_results))
    with pytest.raises(probe.ControlledEvidenceError, match="local_release_dirty"):
        probe._read_release_sha(repo_dir="/opt/linasbot", peer_host=None)


def test_controlled_journal_failure_is_fixed_and_never_echoes_stderr(monkeypatch, capsys) -> None:
    secret = "customer-message-and-provider-id"
    monkeypatch.setattr(
        probe,
        "_run_command",
        lambda _args: SimpleNamespace(returncode=255, stdout="", stderr=secret),
    )
    manifest = _controlled_manifest()
    with pytest.raises(probe.ControlledEvidenceError, match="peer_journal_read_failed"):
        probe._read_controlled_journal(
            node="node02",
            start=manifest.start,
            cutoff=manifest.initial_cutoff,
            peer_host="10.106.0.4",
        )
    assert secret not in capsys.readouterr().out
