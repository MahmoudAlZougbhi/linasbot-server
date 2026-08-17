"""API readiness for request definition graphs (migrated vs missing tables)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, text

from db.models import Base
from db.session import reset_engine_for_tests, whatsapp_session
from services.request_graphs.db_guard import RequestGraphsDbError, graphs_tables_ready, request_graphs_session
from services.request_graphs.service import list_active_graphs, preview_graph, publish_graph


@pytest.fixture()
def migrated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("LINAS_WHATSAPP_ALLOW_SQLITE", "true")
    url = f"sqlite:///{tmp_path / 'graphs_ok.db'}"
    monkeypatch.setenv("LINAS_WHATSAPP_DATABASE_URL", url)
    reset_engine_for_tests()
    engine = create_engine(url, future=True)

    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _connection_record):  # type: ignore[no-untyped-def]
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    yield
    reset_engine_for_tests()


@pytest.fixture()
def empty_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("LINAS_WHATSAPP_ALLOW_SQLITE", "true")
    url = f"sqlite:///{tmp_path / 'graphs_empty.db'}"
    monkeypatch.setenv("LINAS_WHATSAPP_DATABASE_URL", url)
    reset_engine_for_tests()
    engine = create_engine(url, future=True)
    with engine.begin() as conn:
        conn.execute(text("SELECT 1"))
    yield
    reset_engine_for_tests()


SOURCE = "موعد\nجيب الاسم والهاتف"


def test_preview_does_not_need_db() -> None:
    preview = preview_graph(title="موعد", source_text=SOURCE, destination="appointment")
    assert preview["destination"] == "appointment"
    assert preview["needs_owner_clarification"] is False
    assert [row["key"] for row in preview["required_information"]] == ["name", "phone"]


def test_list_succeeds_when_tables_exist(migrated_db: None) -> None:
    with whatsapp_session(require=True) as db:
        assert graphs_tables_ready(db) is True
        assert list_active_graphs(db, tenant_id="t1") == []
        publish_graph(
            db,
            tenant_id="t1",
            source_item_id="req_1",
            title="موعد",
            source_text=SOURCE,
            destination="appointment",
            confirm=True,
        )
        rows = list_active_graphs(db, tenant_id="t1")
    assert len(rows) == 1
    assert rows[0]["source_item_id"] == "req_1"
    assert rows[0]["status"] == "active"


def test_request_graphs_session_rejects_unmigrated(empty_db: None) -> None:
    with pytest.raises(RequestGraphsDbError) as excinfo:
        with request_graphs_session() as db:
            _ = db
    assert excinfo.value.code == "REQUEST_GRAPHS_UNMIGRATED"


def test_publish_round_trip_survives_reload(migrated_db: None) -> None:
    with request_graphs_session() as db:
        first = publish_graph(
            db,
            tenant_id="t1",
            source_item_id="req_keep",
            title="Order",
            source_text="Order\nCollect name and address",
            destination="order",
            confirm=True,
        )
        assert first["status"] == "active"
        definition_id = first["definition_id"]
    with request_graphs_session() as db:
        rows = list_active_graphs(db, tenant_id="t1")
    assert len(rows) == 1
    assert rows[0]["definition_id"] == definition_id
    assert rows[0]["source_item_id"] == "req_keep"
