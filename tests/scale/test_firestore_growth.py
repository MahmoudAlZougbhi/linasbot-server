"""Bounds for shared counters, inbox search, account pages, and thread trim."""

from __future__ import annotations

from typing import Any

import pytest

from services.live_chat.inbox_search import search_index_page
from services.live_chat.index_counter_store import apply_counter_delta, bucket_for_state
from services.team.user_directory_page import list_user_directory_page
from utils.conversation_thread_tail import TAIL_LIMIT, _trim_one_batch


class _Doc:
    def __init__(self, doc_id: str, data: dict[str, Any]) -> None:
        self.id = doc_id
        self._data = data
        self.exists = True

    def to_dict(self) -> dict[str, Any]:
        return dict(self._data)


def test_counter_bucket_collapses_closed_states() -> None:
    assert bucket_for_state("waiting_for_operator") == "waiting"
    assert bucket_for_state("resolved") == "closed"
    assert bucket_for_state("archived") == "closed"


def test_counter_delta_does_not_write_before_the_document_is_ready() -> None:
    class _Ref:
        def get(self, timeout: float | None = None, retry: object = None) -> _Doc:
            del timeout, retry
            return _Doc("linas", {"ready": False})

        def update(self, payload: dict[str, Any]) -> None:
            raise AssertionError(payload)

    class _Collection:
        def document(self, doc_id: str) -> _Ref:
            del doc_id
            return _Ref()

    class _Database:
        def collection(self, name: str) -> Any:
            assert name == "artifacts"
            return self

        def document(self, name: str) -> Any:
            assert name == "linas-ai-bot-backend"
            return self

    db = _Database()
    db.collection = lambda name: db  # type: ignore[method-assign]
    # The counter collection is the third call in the chain. Use a dedicated object.
    counters = _Collection()

    class _App:
        def collection(self, name: str) -> _Collection:
            assert name == "live_chat_index_counters"
            return counters

    class _Root:
        def collection(self, name: str) -> _Root:
            assert name == "artifacts"
            return self

        def document(self, name: str) -> _App:
            assert name == "linas-ai-bot-backend"
            return _App()

    apply_counter_delta(_Root(), "linas", "", "bot_active")


def test_search_pages_forty_documents_and_stops_at_one_hundred_sixty() -> None:
    calls: list[int] = []

    class _Service:
        def _stream_tenant_index_docs(
            self,
            _coll: object,
            _tenant: str,
            *,
            limit: int,
            cursor: str | None = None,
        ) -> list[_Doc]:
            del cursor
            calls.append(limit)
            start = len(calls) * limit
            return [
                _Doc(str(start + offset), {"user_name": "nope", "last_message_at": f"t{start + offset}"})
                for offset in range(limit)
            ]

    page = search_index_page(_Service(), object(), "linas", search="ali", cursor=None, page_size=30)
    assert calls == [40, 40, 40, 40]
    assert page.docs == []
    assert page.has_more is True
    assert page.next_cursor


def test_search_returns_as_soon_as_the_page_is_full() -> None:
    calls: list[int] = []

    class _Service:
        def _stream_tenant_index_docs(
            self,
            _coll: object,
            _tenant: str,
            *,
            limit: int,
            cursor: str | None = None,
        ) -> list[_Doc]:
            del cursor
            calls.append(limit)
            return [_Doc("1", {"user_name": "Ali", "last_message_at": "t1"})]

    page = search_index_page(_Service(), object(), "linas", search="ali", cursor=None, page_size=1)
    assert calls == [40]
    assert [doc.id for doc in page.docs] == ["1"]
    assert page.has_more is True


def test_directory_page_returns_a_cursor_past_the_first_page() -> None:
    docs = [_Doc(f"u{index}", {"email": f"u{index}@x.com", "tenantId": "linas", "role": "owner"}) for index in range(5)]

    class _Query:
        def __init__(self) -> None:
            self.cap = 0
            self.after = ""

        def limit(self, count: int) -> _Query:
            self.cap = count
            return self

        def start_after(self, values: list[str]) -> _Query:
            self.after = values[0]
            return self

        def stream(self, **_kwargs: object) -> list[_Doc]:
            rows = [doc for doc in docs if doc.id > self.after] if self.after else list(docs)
            return rows[: self.cap]

    class _Collection:
        def order_by(self, _name: str) -> _Query:
            return _Query()

    class _Service:
        collection = _Collection()
        AUTH_QUERY_TIMEOUT_SECONDS = 2

        def _sanitize_user(self, data: dict[str, Any], doc_id: str) -> dict[str, Any]:
            return {**data, "id": doc_id}

    first = list_user_directory_page(_Service(), limit=2)
    assert [user["id"] for user in first["users"]] == ["u0", "u1"]
    assert first["has_more"] is True
    assert first["next_cursor"] == "u1"
    second = list_user_directory_page(_Service(), limit=2, cursor=first["next_cursor"])
    assert [user["id"] for user in second["users"]] == ["u2", "u3"]


def test_thread_trim_keeps_the_tail_and_archives_the_older_batch() -> None:
    archived: list[str] = []
    stored = {"messages": [{"message_id": f"m{index}", "text": "hi"} for index in range(TAIL_LIMIT + 5)]}

    class _Messages:
        def document(self, doc_id: str) -> _Messages:
            archived.append(doc_id)
            return self

        def set(self, message: dict[str, Any], merge: bool = False) -> None:
            del message, merge

    class _Ref:
        def get(self, timeout: float | None = None, retry: object = None) -> _Doc:
            del timeout, retry
            return _Doc("conv", stored)

        def collection(self, name: str) -> _Messages:
            assert name == "thread_messages"
            return _Messages()

        def update(self, payload: dict[str, Any]) -> None:
            stored.update(payload)

    assert _trim_one_batch(_Ref()) is False
    assert len(stored["messages"]) == TAIL_LIMIT
    assert archived == [f"m{index}" for index in range(5)]
    assert stored["messages"][0]["message_id"] == "m5"


def test_deletion_peer_does_not_scan_when_the_lock_is_held(monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio

    calls: list[dict[str, Any]] = []

    def process(**kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        return {"examined": 0, "acknowledged": 0, "completed": 0, "pending": 0, "errors": 0, "codes": ["abc"]}

    monkeypatch.setattr(
        "services.scale.job_interval_lock.try_acquire_job_lock",
        lambda name, ttl_seconds=0: name == "meta_deletion_pending_scan" and not calls,
    )
    monkeypatch.setattr("services.scale.job_interval_lock.release_job_lock", lambda _name: None)
    monkeypatch.setattr("services.scale.firestore_quota_backoff.quota_backoff_active", lambda: False)
    monkeypatch.setattr("services.scale.firestore_quota_backoff.note_quota_result", lambda _exc: None)
    monkeypatch.setattr(
        "services.integrations.meta.meta_data_deletion.process_pending_meta_deletion_requests",
        process,
    )
    monkeypatch.setattr("services.integrations.meta.meta_deletion_scan.store_pending_codes", lambda codes: None)
    monkeypatch.setattr("services.integrations.meta.meta_deletion_scan.load_pending_codes", lambda: [])

    from modules.meta_data_deletion_reconcile_job import run_meta_data_deletion_reconcile_job

    asyncio.run(run_meta_data_deletion_reconcile_job())
    asyncio.run(run_meta_data_deletion_reconcile_job())
    assert calls == [{"query_limit": 32}]
