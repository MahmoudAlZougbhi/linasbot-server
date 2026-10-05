"""Postgres chat isolation, Redis claims, and the inbound ledger."""

from __future__ import annotations

import os
import tempfile

import pytest

from db.session import reset_engine_for_tests


class _FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    def ping(self) -> bool:
        return True

    def set(self, key: str, value: str, nx: bool = False, ex: int | None = None) -> bool:
        del ex
        if nx and key in self.store:
            return False
        self.store[key] = value
        return True

    def get(self, key: str) -> str | None:
        return self.store.get(key)

    def delete(self, key: str) -> int:
        return 1 if self.store.pop(key, None) is not None else 0

    def eval(self, script: str, numkeys: int, key: str, *args: str) -> int:
        del numkeys
        current = self.store.get(key)
        if current != args[0]:
            return 0
        if "del" in script and "set" not in script.split("then", 1)[-1]:
            self.store.pop(key, None)
            return 1
        if "expire" in script:
            return 1
        if "set" in script:
            self.store[key] = args[1]
            return 1
        return 0


@pytest.fixture()
def sqlite_db(monkeypatch: pytest.MonkeyPatch):
    handle = tempfile.NamedTemporaryFile(suffix=".sqlite")
    monkeypatch.setenv("LINAS_WHATSAPP_ALLOW_SQLITE", "true")
    monkeypatch.setenv("LINAS_WHATSAPP_DATABASE_URL", f"sqlite:///{handle.name}")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    reset_engine_for_tests()
    yield handle.name
    reset_engine_for_tests()
    handle.close()


def test_tenant_a_cannot_read_tenant_b_inbox(sqlite_db: str) -> None:
    del sqlite_db
    from services.persistence.chat_store import append_message, list_inbox, list_messages

    append_message(
        user_id="alpha:whatsapp:961700001",
        role="user",
        text_body="hello from alpha",
        conversation_id="c-alpha",
        user_name="Alpha",
        metadata={"tenant_id": "alpha"},
    )
    append_message(
        user_id="beta:whatsapp:961700002",
        role="user",
        text_body="hello from beta",
        conversation_id="c-beta",
        user_name="Beta",
        metadata={"tenant_id": "beta"},
    )
    alpha = list_inbox("alpha")
    beta = list_inbox("beta")
    assert [row["conversation_id"] for row in alpha["threads"]] == ["c-alpha"]
    assert [row["conversation_id"] for row in beta["threads"]] == ["c-beta"]
    assert list_messages("alpha", "c-beta") == []
    assert list_messages("beta", "c-alpha") == []


def test_missing_tenant_is_not_written(sqlite_db: str) -> None:
    del sqlite_db
    from services.persistence.chat_store import ChatTenantRequired, append_message

    with pytest.raises(ChatTenantRequired):
        append_message(user_id="961700001", role="user", text_body="no tenant")


def test_duplicate_message_does_not_double_the_count(sqlite_db: str) -> None:
    del sqlite_db
    from services.persistence.chat_store import append_message, list_inbox

    first = append_message(
        user_id="alpha:whatsapp:1",
        role="user",
        text_body="once",
        conversation_id="c1",
        metadata={"message_id": "m1", "tenant_id": "alpha"},
    )
    second = append_message(
        user_id="alpha:whatsapp:1",
        role="user",
        text_body="once",
        conversation_id="c1",
        metadata={"message_id": "m1", "tenant_id": "alpha"},
    )
    assert first["duplicate"] is False
    assert second["duplicate"] is True
    assert list_inbox("alpha")["threads"][0]["message_count"] == 1


def test_redis_claim_is_once_and_only_the_owner_releases() -> None:
    from services.scale.redis_claims import RedisClaimStore

    store = RedisClaimStore(_FakeRedis())
    assert store.try_claim_owner("events", "k", "owner-a", ttl_seconds=30) is True
    assert store.try_claim_owner("events", "k", "owner-b", ttl_seconds=30) is False
    assert store.release_owner("events", "k", "owner-b") is False
    assert store.release_owner("events", "k", "owner-a") is True
    assert store.try_claim_owner("events", "k", "owner-b", ttl_seconds=30) is True


def test_outbound_dedupe_skips_the_second_send(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.scale import outbound_text_firestore_dedupe as dedupe
    from services.scale.redis_claims import RedisClaimStore

    fake = _FakeRedis()
    monkeypatch.setattr(dedupe, "RedisClaimStore", lambda: RedisClaimStore(fake))
    monkeypatch.setenv("OUTBOUND_TEXT_DEDUPE", "true")

    import asyncio

    first = asyncio.run(dedupe.try_acquire_outbound_send_firestore("user-1", "hello"))
    second = asyncio.run(dedupe.try_acquire_outbound_send_firestore("user-1", "hello"))
    assert first
    assert second is None
    asyncio.run(dedupe.release_outbound_send_firestore(first, False))
    third = asyncio.run(dedupe.try_acquire_outbound_send_firestore("user-1", "hello"))
    assert third == first


def test_inbound_ledger_round_trip(sqlite_db: str) -> None:
    del sqlite_db
    from services.persistence.inbound_ledger import get_record, list_active, put_record

    put_record({"event_id": "e1", "tenant_id": "alpha", "state": "accepted", "updated_at": 1})
    put_record({"event_id": "e2", "tenant_id": "beta", "state": "completed", "updated_at": 2})
    assert get_record("e1")["tenant_id"] == "alpha"
    active = list_active()
    assert [row["event_id"] for row in active] == ["e1"]


def test_env_is_isolated(sqlite_db: str) -> None:
    assert os.environ["LINAS_WHATSAPP_DATABASE_URL"].endswith(sqlite_db)
