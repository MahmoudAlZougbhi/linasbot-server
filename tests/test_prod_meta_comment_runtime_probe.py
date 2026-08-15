from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import stat
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import scripts.prod_meta_comment_runtime_probe as probe
from scripts.prod_meta_comment_runtime_probe import REQUIRED_EVIDENCE, missing_required_evidence, scan_evidence


def _complete_evidence_lines() -> list[str]:
    return [
        "[instagram-login] webhook_authenticated object=instagram parsed=1 accepted=1 duplicates=0 comments=0",
        "[meta-evidence] dm_send_accepted channel=facebook auth_flow=facebook_login execution=inline_meta",
        "[meta-evidence] dm_send_accepted channel=instagram auth_flow=instagram_login execution=queue",
        "[meta-evidence] comment_reply_sent channel=facebook auth_flow=facebook_login execution=queue",
        (
            "[meta-evidence] comment_reply_sent channel=instagram "
            "auth_flow=instagram_login execution=inline_instagram_login"
        ),
    ]


def test_strict_evidence_gate_accepts_all_redacted_markers() -> None:
    counts = scan_evidence(_complete_evidence_lines())

    assert missing_required_evidence(counts) == []
    assert counts["fb_dm_send_accepted"] == 1
    assert counts["ig_dm_send_accepted"] == 1
    assert counts["fb_comment_reply_sent"] == 1
    assert counts["ig_comment_reply_sent"] == 1


def test_strict_evidence_gate_reports_each_missing_surface() -> None:
    counts = scan_evidence(
        [
            "[instagram-login] webhook_authenticated object=instagram parsed=1 accepted=1 duplicates=0 comments=0",
            "[meta-evidence] dm_send_accepted channel=facebook auth_flow=facebook_login execution=queue",
        ]
    )

    assert missing_required_evidence(counts) == [
        "direct_instagram_dm_provider_accepted",
        "facebook_comment_reply_provider_accepted",
        "instagram_comment_reply_provider_accepted",
    ]


def test_strict_evidence_gate_rejects_wrong_route_and_non_evidence_lines() -> None:
    counts = scan_evidence(
        [
            "[meta-social] event_processing_completed channel=facebook event_id=secret-id",
            "[meta-evidence] dm_send_accepted channel=instagram auth_flow=facebook_login execution=inline_meta",
            "[meta-comment] reply_sent channel=instagram tenant=linas asset=123456 comment=12345678",
        ]
    )

    assert missing_required_evidence(counts) == list(REQUIRED_EVIDENCE)
    assert counts["ig_dm_send_accepted"] == 0
    assert counts["ig_comment_reply_sent"] == 0


def test_missing_required_evidence_treats_zero_counter_as_missing() -> None:
    assert len(missing_required_evidence(Counter())) == 5


def test_require_evidence_cli_returns_nonzero_when_a_proof_is_missing(monkeypatch) -> None:
    lines = _complete_evidence_lines()[:-1]
    monkeypatch.setattr(
        probe.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(stdout="\n".join(lines), returncode=0),
    )
    monkeypatch.setattr(probe.glob, "glob", lambda _pattern: [])

    assert probe.main(["--require-evidence"]) == 2
    assert probe.main([]) == 0


def test_require_evidence_cli_passes_with_every_proof(monkeypatch) -> None:
    calls: list[list[str]] = []

    def _journal(args, **_kwargs):
        calls.append(args)
        return SimpleNamespace(stdout="\n".join(_complete_evidence_lines()), returncode=0)

    monkeypatch.setattr(
        probe.subprocess,
        "run",
        _journal,
    )
    monkeypatch.setattr(probe.glob, "glob", lambda _pattern: [])

    assert probe.main(["--require-evidence", "--window-minutes", "15"]) == 0
    assert "15 minutes ago" in calls[0]


def test_require_evidence_fails_closed_when_journal_cannot_be_read(monkeypatch) -> None:
    monkeypatch.setattr(
        probe.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(stdout="\n".join(_complete_evidence_lines()), returncode=1),
    )

    assert probe.main(["--require-evidence"]) == 2


def test_strict_evidence_does_not_read_undated_file_tails(monkeypatch) -> None:
    monkeypatch.setattr(
        probe.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(stdout="", returncode=0),
    )
    monkeypatch.setattr(
        probe.glob,
        "glob",
        lambda _pattern: (_ for _ in ()).throw(AssertionError("strict probe read a file tail")),
    )

    assert probe.main(["--require-evidence"]) == 2


def test_strict_evidence_rejects_a_week_wide_window() -> None:
    with pytest.raises(SystemExit) as error:
        probe._parse_args(["--require-evidence", "--window-minutes", "10080"])

    assert error.value.code == 2


def test_runtime_probe_workflow_passes_window_through_the_action_environment() -> None:
    workflow = Path(".github/workflows/meta-comment-runtime-probe.yml").read_text()

    assert "META_EVIDENCE_WINDOW_MINUTES: ${{ inputs.window_minutes }}" in workflow
    assert "META_EVIDENCE_MODE: ${{ inputs.mode }}" in workflow
    assert "META_EVIDENCE_MANIFEST_PATH: ${{ inputs.manifest_path }}" in workflow
    assert "META_EVIDENCE_MANIFEST_SHA256: ${{ inputs.manifest_sha256 }}" in workflow
    assert "META_EVIDENCE_INITIAL_ATTESTATION_SHA256: ${{ inputs.initial_attestation_sha256 }}" in workflow
    assert "META_EVIDENCE_REPLAY_ATTESTATION_SHA256: ${{ inputs.replay_attestation_sha256 }}" in workflow
    assert '--window-minutes "$META_EVIDENCE_WINDOW_MINUTES"' in workflow
    assert '--window-minutes "${{ inputs.window_minutes }}"' not in workflow
    assert '--controlled-manifest "$META_EVIDENCE_MANIFEST_PATH"' in workflow
    assert '--manifest-sha256 "$META_EVIDENCE_MANIFEST_SHA256"' in workflow
    assert '--initial-attestation-sha256 "$META_EVIDENCE_INITIAL_ATTESTATION_SHA256"' in workflow
    assert '--replay-attestation-sha256 "$META_EVIDENCE_REPLAY_ATTESTATION_SHA256"' in workflow
    assert '--expected-release-sha "$EXPECTED_RELEASE_SHA"' in workflow


def test_ha_probe_aggregates_markers_across_both_nodes(monkeypatch) -> None:
    node01 = _complete_evidence_lines()[:2]
    node02 = _complete_evidence_lines()[2:]
    results = iter(
        [
            SimpleNamespace(stdout="\n".join(node01), returncode=0),
            SimpleNamespace(stdout="\n".join(node02), returncode=0),
        ]
    )
    monkeypatch.setattr(probe.subprocess, "run", lambda *_args, **_kwargs: next(results))

    assert probe.main(["--require-evidence", "--include-ha-peer"]) == 0


def test_ha_probe_fails_closed_when_peer_journal_is_unavailable(monkeypatch) -> None:
    results = iter(
        [
            SimpleNamespace(stdout="\n".join(_complete_evidence_lines()), returncode=0),
            SimpleNamespace(stdout="", returncode=255),
        ]
    )
    monkeypatch.setattr(probe.subprocess, "run", lambda *_args, **_kwargs: next(results))

    assert probe.main(["--require-evidence", "--include-ha-peer"]) == 2


EVENTS = {
    "facebook_dm": "ibe_" + "1" * 40,
    "instagram_dm": "ibe_" + "2" * 40,
    "facebook_comment": "ibe_" + "3" * 40,
    "instagram_comment": "ibe_" + "4" * 40,
}
BINDINGS = {
    "facebook_dm": "5" * 64,
    "instagram_dm": "6" * 64,
    "facebook_comment": "7" * 64,
    "instagram_comment": "8" * 64,
}
RELEASE_SHA = "a" * 40
FAILOVER_TX = "mft_" + "f" * 64
NODE_KEYS = {node: Ed25519PrivateKey.generate() for node in probe.REQUIRED_NODES}


def _manifest_bytes(
    *,
    start: datetime | None = None,
    initial_cutoff: datetime | None = None,
    final_cutoff: datetime | None = None,
    events: dict[str, str] | None = None,
    bindings: dict[str, str] | None = None,
    release_sha: str = RELEASE_SHA,
) -> bytes:
    start = start or datetime(2026, 8, 14, 12, 0, tzinfo=UTC)
    initial_cutoff = initial_cutoff or start + timedelta(minutes=10)
    final_cutoff = final_cutoff or initial_cutoff + timedelta(minutes=5)
    document = {
        "schema": probe.CONTROLLED_SCHEMA,
        "test_run_id": "mtr_" + "b" * 64,
        "release_sha": release_sha,
        "window": {
            "start": start.isoformat().replace("+00:00", "Z"),
            "initial_cutoff": initial_cutoff.isoformat().replace("+00:00", "Z"),
            "final_cutoff": final_cutoff.isoformat().replace("+00:00", "Z"),
        },
        "retry_observation_seconds": 300,
        "events": events or EVENTS,
        "bindings": bindings or BINDINGS,
        "topology": {
            "failover_transaction_id": FAILOVER_TX,
            "initial_node": "node01",
            "replay_node": "node02",
        },
    }
    return json.dumps(document, separators=(",", ":"), sort_keys=True).encode()


def _controlled_manifest(**kwargs) -> probe.ControlledManifest:
    return probe.parse_controlled_manifest(_manifest_bytes(**kwargs))


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _verification_keys():
    return {node: key.public_key() for node, key in NODE_KEYS.items()}


def _attestation_bytes(
    manifest: probe.ControlledManifest,
    manifest_sha256: str,
    *,
    phase: str,
) -> bytes:
    if phase == "initial":
        started = manifest.start - timedelta(seconds=60)
        proved = manifest.start - timedelta(seconds=30)
        states = {"node01": (200, False), "node02": (503, True)}
    else:
        started = manifest.initial_cutoff + timedelta(seconds=1)
        proved = started + timedelta(seconds=30)
        states = {"node01": (503, True), "node02": (200, False)}
    node_proofs: dict[str, dict[str, object]] = {}
    for index, node in enumerate(probe.REQUIRED_NODES, start=1):
        status, maintenance = states[node]
        body: dict[str, object] = {
            "node_id": node,
            "phase": phase,
            "transaction_id": manifest.failover_transaction_id,
            "release_sha": manifest.release_sha,
            "direct_ready_status": status,
            "maintenance": maintenance,
            "observed_at": proved.isoformat().replace("+00:00", "Z"),
            "machine_id_sha256": str(index) * 64,
        }
        node_proofs[node] = {
            **body,
            "node_signature": _b64(NODE_KEYS[node].sign(probe._canonical_json(body))),
        }
    body = {
        "schema": probe.FAILOVER_SCHEMA,
        "phase": phase,
        "transaction_id": manifest.failover_transaction_id,
        "test_run_id": manifest.test_run_id,
        "manifest_sha256": manifest_sha256,
        "release_sha": manifest.release_sha,
        "initial_node": manifest.initial_node,
        "replay_node": manifest.replay_node,
        "lb_ready_projection_sha256": "d" * 64,
        "lb_pre_attestation_sha256": "a" * 64,
        "lb_post_attestation_sha256": "b" * 64,
        "lb_post_observed_at": proved.isoformat().replace("+00:00", "Z"),
        "phase_started_at": started.isoformat().replace("+00:00", "Z"),
        "phase_proved_at": proved.isoformat().replace("+00:00", "Z"),
        "minimum_drain_seconds": 25,
        "public_ready_status": 200,
        "node_proofs": node_proofs,
    }
    signed = {
        **body,
        "coordinator_signature": _b64(NODE_KEYS["node01"].sign(probe._canonical_json(body))),
    }
    return json.dumps(signed, separators=(",", ":"), sort_keys=True).encode()


def _marker(
    surface: str,
    outcome: str,
    *,
    event_id: str | None = None,
    node: str = "node01",
) -> probe.ControlledMarker:
    return probe.ControlledMarker(
        node=node,
        occurred_at=datetime(2026, 8, 14, 12, 5, tzinfo=UTC),
        surface=surface,
        outcome=outcome,
        event_id=event_id or EVENTS[surface],
    )


def _complete_controlled_markers() -> list[probe.ControlledMarker]:
    return [
        _marker("facebook_dm", "provider_accepted"),
        _marker("instagram_dm", "instagram_login_authenticated"),
        _marker("instagram_dm", "provider_accepted"),
        _marker("facebook_comment", "provider_accepted"),
        _marker("instagram_comment", "instagram_login_authenticated"),
        _marker("instagram_comment", "provider_accepted"),
    ]


def test_controlled_gate_requires_exact_one_correlated_success_per_surface() -> None:
    passed, summary, reasons = probe.evaluate_controlled_markers(
        _controlled_manifest(),
        _complete_controlled_markers(),
    )

    assert passed is True
    assert reasons == []
    assert summary["facebook_dm"]["provider_accepted"] == 1
    assert summary["instagram_dm"]["instagram_login_authenticated"] == 1


def _complete_attempt_documents() -> dict[str, dict[str, object]]:
    return {
        event_id: {
            "schema_version": 1,
            "event_id": event_id,
            "surface": surface,
            "status": "accepted",
            "attempt_sequence": 1,
            "provider_message_id_sha256": "a" * 64,
            "binding_id_sha256": BINDINGS[surface],
        }
        for surface, event_id in EVENTS.items()
    }


def test_controlled_gate_requires_first_shared_attempt_with_provider_hash() -> None:
    manifest = _controlled_manifest()
    documents = _complete_attempt_documents()
    passed, summary, reasons = probe.evaluate_controlled_attempt_documents(manifest, documents)
    assert passed is True
    assert reasons == []
    assert summary["facebook_dm"]["attempt_sequence"] == 1

    documents[EVENTS["facebook_dm"]]["attempt_sequence"] = 2
    passed, _summary, reasons = probe.evaluate_controlled_attempt_documents(manifest, documents)
    assert passed is False
    assert reasons == ["facebook_dm_shared_attempt_invalid"]

    documents = _complete_attempt_documents()
    documents[EVENTS["instagram_comment"]]["provider_message_id_sha256"] = ""
    passed, _summary, reasons = probe.evaluate_controlled_attempt_documents(manifest, documents)
    assert passed is False
    assert reasons == ["instagram_comment_shared_attempt_invalid"]


def test_controlled_gate_rejects_an_event_sent_through_the_wrong_binding() -> None:
    manifest = _controlled_manifest()
    documents = _complete_attempt_documents()
    documents[EVENTS["instagram_dm"]]["binding_id_sha256"] = "9" * 64

    passed, summary, reasons = probe.evaluate_controlled_attempt_documents(manifest, documents)

    assert passed is False
    assert reasons == ["instagram_dm_binding_mismatch"]
    assert summary["instagram_dm"]["binding_hash_matches_expected"] is False


def test_controlled_gate_rejects_duplicate_and_cross_node_success() -> None:
    markers = _complete_controlled_markers()
    markers.append(_marker("facebook_dm", "provider_accepted", node="node02"))

    passed, _summary, reasons = probe.evaluate_controlled_markers(_controlled_manifest(), markers)

    assert passed is False
    assert "facebook_dm_provider_acceptance_count" in reasons
    assert "facebook_dm_cross_node_duplicate" in reasons


def test_controlled_gate_rejects_same_node_duplicate_success() -> None:
    markers = _complete_controlled_markers()
    markers.append(_marker("facebook_comment", "provider_accepted", node="node01"))

    passed, _summary, reasons = probe.evaluate_controlled_markers(_controlled_manifest(), markers)

    assert passed is False
    assert "facebook_comment_provider_acceptance_count" in reasons
    assert "facebook_comment_cross_node_duplicate" not in reasons


def test_controlled_gate_rejects_wrong_event_and_wrong_surface() -> None:
    markers = _complete_controlled_markers()
    markers[0] = _marker("facebook_dm", "provider_accepted", event_id="ibe_" + "9" * 40)
    markers.append(_marker("instagram_dm", "provider_accepted", event_id=EVENTS["facebook_dm"]))

    passed, _summary, reasons = probe.evaluate_controlled_markers(_controlled_manifest(), markers)

    assert passed is False
    assert "facebook_dm_provider_acceptance_count" in reasons
    assert "facebook_dm_surface_mismatch" in reasons


@pytest.mark.parametrize("outcome", ["failed", "retry", "second_send"])
def test_controlled_gate_rejects_negative_outcome_for_expected_event(outcome: str) -> None:
    markers = _complete_controlled_markers()
    markers.append(_marker("instagram_comment", outcome, node="node02"))

    passed, _summary, reasons = probe.evaluate_controlled_markers(_controlled_manifest(), markers)

    assert passed is False
    assert "instagram_comment_forbidden_outcome" in reasons


def test_controlled_gate_reports_but_does_not_mislabel_suppressed_duplicate() -> None:
    markers = _complete_controlled_markers()
    markers.append(_marker("instagram_comment", "duplicate_suppressed", node="node02"))

    passed, summary, reasons = probe.evaluate_controlled_markers(_controlled_manifest(), markers)

    assert passed is True
    assert reasons == []
    assert summary["instagram_comment"]["duplicate_suppressed"] == 1


def test_final_controlled_gate_requires_correlated_post_initial_replay_for_every_surface() -> None:
    manifest = _controlled_manifest()
    initial = _complete_controlled_markers()

    passed, _summary, reasons = probe.evaluate_controlled_markers(
        manifest,
        initial,
        replay_after=manifest.initial_cutoff,
    )
    assert passed is False
    assert set(reasons) == {f"{surface}_post_initial_replay_count" for surface in probe.CONTROLLED_SURFACES}

    replays = [
        probe.ControlledMarker(
            node="node02",
            occurred_at=manifest.initial_cutoff + timedelta(seconds=30 + index),
            surface=surface,
            outcome="duplicate_suppressed",
            event_id=EVENTS[surface],
        )
        for index, surface in enumerate(probe.CONTROLLED_SURFACES)
    ]
    passed, summary, reasons = probe.evaluate_controlled_markers(
        manifest,
        [*initial, *replays],
        replay_after=manifest.initial_cutoff,
    )
    assert passed is True
    assert reasons == []
    assert all(summary[surface]["post_initial_duplicate_suppressed"] == 1 for surface in probe.CONTROLLED_SURFACES)


def test_final_controlled_gate_rejects_same_node_only_replays() -> None:
    manifest = _controlled_manifest()
    replays = [
        probe.ControlledMarker(
            node="node01",
            occurred_at=manifest.initial_cutoff + timedelta(seconds=30 + index),
            surface=surface,
            outcome="duplicate_suppressed",
            event_id=EVENTS[surface],
        )
        for index, surface in enumerate(probe.CONTROLLED_SURFACES)
    ]

    passed, _summary, reasons = probe.evaluate_controlled_markers(
        manifest,
        [*_complete_controlled_markers(), *replays],
        replay_after=manifest.initial_cutoff,
    )

    assert passed is False
    assert set(reasons) == {f"{surface}_replay_node_mismatch" for surface in probe.CONTROLLED_SURFACES}


def test_controlled_gate_requires_dedicated_ig_auth_tied_to_each_expected_event() -> None:
    markers = [item for item in _complete_controlled_markers() if item.outcome != "instagram_login_authenticated"]
    markers.append(
        _marker(
            "instagram_dm",
            "instagram_login_authenticated",
            event_id="ibe_" + "8" * 40,
        )
    )

    passed, _summary, reasons = probe.evaluate_controlled_markers(_controlled_manifest(), markers)

    assert passed is False
    assert "instagram_dm_dedicated_auth_count" in reasons
    assert "instagram_comment_dedicated_auth_count" in reasons


def test_manifest_rejects_wrong_sha_wide_window_and_short_retry_window(monkeypatch) -> None:
    raw = _manifest_bytes()
    monkeypatch.setattr(probe.sys, "stdin", SimpleNamespace(buffer=io.BytesIO(raw)))
    with pytest.raises(probe.ControlledEvidenceError, match="manifest_hash_mismatch"):
        probe.read_controlled_manifest("-", "0" * 64)

    start = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)
    with pytest.raises(probe.ControlledEvidenceError, match="manifest_window_too_wide"):
        _controlled_manifest(
            start=start,
            initial_cutoff=start + timedelta(minutes=10),
            final_cutoff=start + timedelta(minutes=61),
        )
    with pytest.raises(probe.ControlledEvidenceError, match="manifest_retry_window_too_short"):
        _controlled_manifest(
            start=start,
            initial_cutoff=start + timedelta(minutes=10),
            final_cutoff=start + timedelta(minutes=14),
        )


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


def _journal_json(message: str, occurred_at: datetime) -> str:
    timestamp = int(occurred_at.timestamp() * 1_000_000)
    return json.dumps({"MESSAGE": message, "__REALTIME_TIMESTAMP": str(timestamp)})


def _marker_message(marker: probe.ControlledMarker) -> str:
    return f"[meta-evidence-v2] event surface={marker.surface} outcome={marker.outcome} event_id={marker.event_id}"


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
