"""Equality filters, order, and limit run in SQL."""

from __future__ import annotations

import pytest


@pytest.fixture()
def documents(monkeypatch: pytest.MonkeyPatch, tmp_path):
    from db.session import reset_engine_for_tests

    monkeypatch.setenv("LINAS_WHATSAPP_ALLOW_SQLITE", "true")
    monkeypatch.setenv("LINAS_WHATSAPP_DATABASE_URL", f"sqlite:///{tmp_path}/docs.sqlite")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    reset_engine_for_tests()
    yield
    reset_engine_for_tests()


def test_equality_limit_does_not_scan_the_parent(documents, monkeypatch: pytest.MonkeyPatch) -> None:
    del documents
    from services.persistence.document_store import open_document_client

    client = open_document_client()
    assert client is not None
    collection = client.collection("artifacts").document("backend").collection("users")
    for index in range(5):
        collection.document(f"user-{index}").set({"tenantId": "a" if index == 3 else "b", "n": index})

    def _full_scan(*_args, **_kwargs):
        raise AssertionError("parent scan")

    monkeypatch.setattr(client, "children", _full_scan)
    rows = collection.where("tenantId", "==", "a").limit(1).stream()
    assert len(rows) == 1
    assert rows[0].to_dict()["tenantId"] == "a"


def test_order_and_limit_run_in_sql(documents, monkeypatch: pytest.MonkeyPatch) -> None:
    del documents
    from services.persistence.document_store import open_document_client

    client = open_document_client()
    assert client is not None
    collection = client.collection("items")
    for name in ("c", "a", "b"):
        collection.document(name).set({"label": name})

    def _full_scan(*_args, **_kwargs):
        raise AssertionError("parent scan")

    monkeypatch.setattr(client, "children", _full_scan)
    rows = collection.order_by("label").limit(2).stream()
    assert [row.to_dict()["label"] for row in rows] == ["a", "b"]
