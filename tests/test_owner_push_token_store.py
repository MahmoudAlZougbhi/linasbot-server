"""Direct tests for OwnerPushTokenStore tenant fail-closed behavior."""

from __future__ import annotations

from pathlib import Path

import pytest

from services.owner_push_token_store import OwnerPushTokenStore


@pytest.fixture
def store(tmp_path: Path) -> OwnerPushTokenStore:
    return OwnerPushTokenStore(root=tmp_path / "tokens")


@pytest.mark.parametrize("tenant_id", [None, "", "   ", "\t"])
def test_owner_push_token_store_rejects_missing_tenant(
    store: OwnerPushTokenStore,
    tenant_id: str | None,
) -> None:
    with pytest.raises(ValueError, match="tenant_id required"):
        store.upsert(
            tenant_id=tenant_id,  # type: ignore[arg-type]
            user_id="u1",
            token="tok",
        )
    with pytest.raises(ValueError, match="tenant_id required"):
        store.list_tokens(tenant_id=tenant_id)  # type: ignore[arg-type]


def test_owner_push_token_store_explicit_linas(store: OwnerPushTokenStore) -> None:
    row = store.upsert(tenant_id="linas", user_id="u1", token="ExponentPushToken[abc]")
    assert row["token"] == "ExponentPushToken[abc]"
    tokens = store.list_tokens(tenant_id="linas")
    assert len(tokens) == 1
    assert tokens[0]["user_id"] == "u1"
