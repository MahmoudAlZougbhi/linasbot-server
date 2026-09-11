"""Shared helpers for production Meta comment runtime probe tests."""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import scripts.prod_meta_comment_runtime_probe as probe


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


def _journal_json(message: str, occurred_at: datetime) -> str:
    timestamp = int(occurred_at.timestamp() * 1_000_000)
    return json.dumps({"MESSAGE": message, "__REALTIME_TIMESTAMP": str(timestamp)})


def _marker_message(marker: probe.ControlledMarker) -> str:
    return f"[meta-evidence-v2] event surface={marker.surface} outcome={marker.outcome} event_id={marker.event_id}"
