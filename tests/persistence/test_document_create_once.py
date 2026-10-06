"""create() inserts once even when callers race."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from services.persistence.query_api import AlreadyExists


@pytest.fixture()
def documents(monkeypatch: pytest.MonkeyPatch, tmp_path):
    from db.session import reset_engine_for_tests

    monkeypatch.setenv("LINAS_WHATSAPP_ALLOW_SQLITE", "true")
    monkeypatch.setenv("LINAS_WHATSAPP_DATABASE_URL", f"sqlite:///{tmp_path}/docs.sqlite")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    reset_engine_for_tests()
    yield
    reset_engine_for_tests()


def test_concurrent_create_allows_one_writer(documents) -> None:
    del documents
    from services.persistence.document_store import open_document_client

    client = open_document_client()
    assert client is not None
    ref = client.collection("artifacts").document("backend").collection("events").document("evt-1")

    def _create() -> str:
        try:
            ref.create({"ok": True})
        except AlreadyExists:
            return "exists"
        return "created"

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: _create(), range(8)))
    assert results.count("created") == 1
    assert results.count("exists") == 7
    assert ref.get().exists
