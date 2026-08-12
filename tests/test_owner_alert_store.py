"""Direct tests for OwnerAlertStore tenant fail-closed behavior."""

from __future__ import annotations

from pathlib import Path

import pytest

from services.owner_alert_store import OwnerAlertStore


@pytest.fixture
def store(tmp_path: Path) -> OwnerAlertStore:
    return OwnerAlertStore(root=tmp_path / "alerts")


@pytest.mark.parametrize("tenant_id", [None, "", "   ", "\t"])
def test_owner_alert_store_rejects_missing_tenant(
    store: OwnerAlertStore,
    tenant_id: str | None,
) -> None:
    with pytest.raises(ValueError, match="tenant_id required"):
        store.create(tenant_id=tenant_id, payload={"type": "test"})  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="tenant_id required"):
        store.list_alerts(tenant_id=tenant_id)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="tenant_id required"):
        store.unread_count(tenant_id=tenant_id)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="tenant_id required"):
        store.get(tenant_id=tenant_id, alert_id="abc")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="tenant_id required"):
        store.mark_read(tenant_id=tenant_id, alert_id="abc")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="tenant_id required"):
        store.mark_all_read(tenant_id=tenant_id)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="tenant_id required"):
        store.recent_duplicate(
            tenant_id=tenant_id,  # type: ignore[arg-type]
            alert_type="test",
            conversation_id="c1",
            user_id="u1",
        )


def test_owner_alert_store_explicit_linas(store: OwnerAlertStore) -> None:
    record = store.create(tenant_id="linas", payload={"type": "test", "message": "hi"})
    assert record["tenant_id"] == "linas"
    items = store.list_alerts(tenant_id="linas")
    assert len(items) == 1
    assert items[0]["id"] == record["id"]
