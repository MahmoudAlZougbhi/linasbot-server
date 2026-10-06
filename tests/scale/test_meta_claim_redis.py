"""Redis owner claims: expiry, stale owner, live watchdog skip, and deletion fence."""

from __future__ import annotations

from pathlib import Path

import pytest

import services.scale.durable_event_claim as claims
import services.scale.inbound_event_reconcile as reconcile
import services.scale.inbound_event_store as event_store
from services.scale.redis_claims import RedisClaimStore
from tests.meta_compliance_helpers import _FakeFirestore
from tests.scale.memory_claim_redis import install_memory_claim_store
from tests.scale.test_meta_inbound_atomicity import _record


@pytest.fixture()
def shared_ledger(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[_FakeFirestore, Path]:
    import utils.utils

    db = _FakeFirestore()
    root = tmp_path / "inbound"
    root.mkdir()
    monkeypatch.setattr(event_store, "_store_dir", lambda: root)
    monkeypatch.setattr(utils.utils, "get_document_db", lambda: db)
    monkeypatch.setenv("ENVIRONMENT", "production")
    install_memory_claim_store(monkeypatch)
    return db, root


@pytest.mark.asyncio
async def test_expired_firestore_claim_can_be_recovered_after_claim_owner_crash(
    shared_ledger: tuple[_FakeFirestore, Path],
) -> None:
    del shared_ledger
    claim_collection = "meta_social_dm_global_claims"
    namespace = "meta_social_dm_global"
    key = "facebook:provider-mid-crash"

    assert await claims.try_claim_event(
        namespace,
        key,
        ttl_seconds=300,
        firestore_collection=claim_collection,
    )
    assert (
        await claims.try_claim_event(
            namespace,
            key,
            ttl_seconds=300,
            firestore_collection=claim_collection,
        )
        is False
    )
    RedisClaimStore().release_claim(namespace, key)
    assert await claims.try_claim_event(
        namespace,
        key,
        ttl_seconds=300,
        firestore_collection=claim_collection,
    )


@pytest.mark.asyncio
async def test_released_firestore_claim_can_be_reacquired_by_new_generation(
    shared_ledger: tuple[_FakeFirestore, Path],
) -> None:
    del shared_ledger
    namespace = "meta_social_dm_global"
    collection = "meta_social_dm_global_claims"
    key = "facebook:provider-mid-retry"

    first = await claims.try_claim_event_handle(
        namespace,
        key,
        firestore_collection=collection,
    )
    assert first is not None
    await claims.release_event_claim(
        namespace,
        key,
        firestore_collection=collection,
        claim_handle=first,
    )

    second = await claims.try_claim_event_handle(
        namespace,
        key,
        firestore_collection=collection,
    )
    assert second is not None
    assert second.owner_token != first.owner_token

    await claims.complete_event_claim(
        namespace,
        key,
        firestore_collection=collection,
        claim_handle=first,
    )
    await claims.release_event_claim(
        namespace,
        key,
        firestore_collection=collection,
        claim_handle=first,
    )
    assert (
        await claims.try_claim_event_handle(
            namespace,
            key,
            firestore_collection=collection,
        )
        is None
    )
    await claims.release_event_claim(
        namespace,
        key,
        firestore_collection=collection,
        claim_handle=second,
    )


@pytest.mark.asyncio
async def test_watchdog_never_bumps_or_dead_letters_event_with_live_owner(
    shared_ledger: tuple[_FakeFirestore, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del shared_ledger
    event_id = "ibe_" + "4" * 40
    rec = _record(event_id=event_id, state="processing")
    rec.attempts = 7
    namespace = "meta_social_dm_global"
    collection = "meta_social_dm_global_claims"
    live = await claims.try_claim_event_handle(
        namespace,
        rec.claim_key,
        ttl_seconds=300,
        firestore_collection=collection,
    )
    assert live is not None
    monkeypatch.setattr(reconcile, "list_active_inbound_events", lambda **_kwargs: [rec])
    monkeypatch.setattr(reconcile, "accountability_stats", lambda: {"unexplained_missing_events": 0})
    transitions: list[dict[str, object]] = []
    monkeypatch.setattr(
        reconcile,
        "mark_inbound_state",
        lambda *_args, **kwargs: transitions.append(kwargs),
    )

    for _ in range(12):
        result = reconcile.reconcile_stuck_inbound_events(older_than_seconds=0)
        assert result["actions"] == [{"event_id": event_id, "action": "live_claim_skipped"}]

    assert rec.attempts == 7
    assert transitions == []


@pytest.mark.asyncio
async def test_binding_fence_prevents_new_ai_or_global_claim(
    shared_ledger: tuple[_FakeFirestore, Path],
) -> None:
    db, _ = shared_ledger
    binding_id = "binding-deletion-fenced"
    from services.integrations.meta.meta_inbound_deletion_fence import firestore_binding_deletion_fence_ref

    firestore_binding_deletion_fence_ref(db, binding_id).set({"status": "fenced"})
    handle = await claims.try_claim_event_handle(
        "ai_turn_claims",
        "private-key-basis",
        firestore_collection="ai_turn_claims",
        meta_binding_id=binding_id,
        firestore_claim_metadata={"binding_id_sha256": claims.meta_claim_binding_digest(binding_id)},
    )

    assert handle is None
