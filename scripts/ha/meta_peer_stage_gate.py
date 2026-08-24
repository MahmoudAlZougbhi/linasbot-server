"""Peer-node staging gate for Meta HA commit-via-restart transactions."""

from __future__ import annotations

from pathlib import Path

from scripts.ha import sync_meta_env_to_peer as sync


def require_peer_stage_authority(
    state_root: Path,
    *,
    expected_sha: str,
) -> dict[str, object]:
    sync._refuse_conflicting_ha_transaction(state_root)
    sync._require_node_identity(sync.ENV_PATH, sync.PEER_NODE_ID)
    if sync._load_journal(state_root) is not None:
        raise RuntimeError("Meta HA environment staging has already been consumed")
    sync._ensure_maintenance_armed(state_root)
    worker_state = sync._load_worker_state(state_root)
    if worker_state is None:
        raise RuntimeError("Peer Meta pre-stage worker state is absent")
    if (
        worker_state["role"] != "peer"
        or worker_state["expected_sha"] != expected_sha
        or worker_state["status"] != "quiesced"
    ):
        raise RuntimeError("Peer Meta pre-stage worker state does not match durable authority")
    current_fingerprint = sync._meta_fingerprint(
        sync._read_meta_values(sync.ENV_PATH),
        expected_sha,
    )
    if current_fingerprint != worker_state["old_fingerprint"]:
        raise RuntimeError("Peer canonical environment changed before staging")
    sync._verify_worker_units_quiesced()
    return worker_state
