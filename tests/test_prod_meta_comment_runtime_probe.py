"""Production Meta comment runtime probe evidence and controlled-gate tests."""

from __future__ import annotations

import io
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

import scripts.prod_meta_comment_runtime_probe as probe
from scripts.prod_meta_comment_runtime_probe import REQUIRED_EVIDENCE, missing_required_evidence, scan_evidence
from tests.prod_meta_comment_runtime_probe_support import (
    EVENTS,
    _complete_attempt_documents,
    _complete_controlled_markers,
    _complete_evidence_lines,
    _controlled_manifest,
    _manifest_bytes,
    _marker,
)

pytest_plugins = ("tests.prod_meta_comment_runtime_probe_support",)


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


def test_controlled_gate_requires_exact_one_correlated_success_per_surface() -> None:
    passed, summary, reasons = probe.evaluate_controlled_markers(
        _controlled_manifest(),
        _complete_controlled_markers(),
    )

    assert passed is True
    assert reasons == []
    assert summary["facebook_dm"]["provider_accepted"] == 1
    assert summary["instagram_dm"]["instagram_login_authenticated"] == 1


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
