"""Combine flush must keep Meta mids after draining Redis."""

from __future__ import annotations

from pathlib import Path

import pytest

from services.queues.combine_flush_handler import apply_drained_chunk_identity


def test_apply_drained_chunk_identity_copies_mids_and_event_ids() -> None:
    user_data: dict[str, object] = {"tenant_id": "linas", "channel": "facebook"}
    apply_drained_chunk_identity(
        user_data,
        [
            {"text": "Hello", "mid": "mid-a", "event_id": "ibe_a"},
            {"text": "again", "mid": "mid-b", "event_id": "ibe_b"},
        ],
    )
    assert user_data["_batch_inbound_mids"] == ["mid-a", "mid-b"]
    assert user_data["_combine_mid"] == "mid-b"
    assert user_data["_inbound_event_id"] == "ibe_b"
    assert user_data["_combine_event_ids"] == ["ibe_a", "ibe_b"]


def test_apply_drained_chunk_identity_uses_event_ids_when_mids_missing() -> None:
    user_data: dict[str, object] = {}
    apply_drained_chunk_identity(user_data, [{"text": "hi", "mid": "", "event_id": "ibe_only"}])
    assert user_data.get("_batch_inbound_mids") is None
    assert user_data["_inbound_event_id"] == "ibe_only"
    assert user_data["_combine_event_ids"] == ["ibe_only"]


def test_ensure_turn_started_falls_back_to_inbound_event_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    turns = tmp_path / "ai_reply_turns"
    turns.mkdir()
    import services.ai_reply_lifecycle as lifecycle

    monkeypatch.setattr(lifecycle, "_store_dir", lambda: turns)
    from services.ai_reply_turn_runtime import ensure_turn_started

    user_data = {"tenant_id": "linas", "channel": "facebook", "_inbound_event_id": "ibe_fb_1"}
    lid = ensure_turn_started(user_data)
    assert lid
    assert user_data["_logical_reply_id"] == lid
