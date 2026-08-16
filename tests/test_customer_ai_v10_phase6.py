"""Customer AI V10 Phase 6 — Request Definition Graph."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event

from db.models import Base
from db.session import reset_engine_for_tests, whatsapp_session
from services.customer_reply_v2.retrieval_request_dispatch import dispatch_request_graph_tool
from services.customer_reply_v2.retrieval_tools import ToolContext
from services.request_graphs.compiler import compile_request_graph
from services.request_graphs.service import (
    delete_graph,
    get_active_graph,
    list_active_graphs,
    preview_graph,
    publish_graph,
    sync_graphs_from_request_rules,
)

SOURCE = "موعد Full Body\nإذا الزبون بده موعد، جيب الاسم والعمر والطول والوزن والمنطقة واليوم المطلوب."


@pytest.fixture()
def graph_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("LINAS_WHATSAPP_ALLOW_SQLITE", "true")
    url = f"sqlite:///{tmp_path / 'graphs.db'}"
    monkeypatch.setenv("LINAS_WHATSAPP_DATABASE_URL", url)
    reset_engine_for_tests()
    engine = create_engine(url, future=True)

    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _connection_record):  # type: ignore[no-untyped-def]
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    yield
    reset_engine_for_tests()


def test_compile_named_fields_and_skips_appointment_substring() -> None:
    compiled = compile_request_graph(title="موعد Full Body", source_text=SOURCE, destination="APPOINTMENT")
    keys = [row["key"] for row in compiled.required_information]
    assert keys == ["name", "age", "height", "weight", "area", "day"]
    assert compiled.destination == "appointment"
    assert compiled.needs_owner_clarification is False
    assert compiled.used_llm is False
    assert compiled.effective_reasoning_effort == "medium"
    assert compiled.requested_reasoning_effort in {"low", "medium"}
    assert compiled.requested_reasoning_effort != "high"


def test_vague_owner_text_does_not_invent_fields() -> None:
    compiled = compile_request_graph(
        title="موعد",
        source_text="جيب كل المعلومات المهمة",
        destination="APPOINTMENT",
        llm_result={
            "required_information": [{"key": "national_id", "label": "رقم وطني", "value_type": "string"}],
            "effort": "high",
        },
    )
    assert compiled.needs_owner_clarification is True
    assert compiled.required_information == []
    assert compiled.used_llm is False
    preview = preview_graph(title="موعد", source_text="جيب كل المعلومات المهمة")
    assert preview["needs_owner_clarification"] is True
    assert preview["metering"]["is_ai"] is False


def test_llm_cannot_invent_ungrounded_fields() -> None:
    compiled = compile_request_graph(
        title="موعد",
        source_text="جيب الاسم فقط",
        destination="APPOINTMENT",
        llm_result={
            "required_information": [
                {"key": "name", "label": "الاسم", "value_type": "string"},
                {"key": "national_id", "label": "رقم وطني", "value_type": "string"},
            ],
            "effort": "xhigh",
        },
    )
    assert compiled.used_llm is True
    assert [row["key"] for row in compiled.required_information] == ["name"]
    assert compiled.effective_reasoning_effort == "low"


def test_preview_does_not_persist(graph_env: None) -> None:
    preview_graph(title="موعد", source_text=SOURCE, destination="APPOINTMENT")
    with whatsapp_session(require=True) as db:
        assert list_active_graphs(db, tenant_id="t1") == []


def test_publish_requires_confirm_then_same_definition_on_edit(graph_env: None) -> None:
    with whatsapp_session(require=True) as db:
        unconfirmed = publish_graph(
            db,
            tenant_id="t1",
            source_item_id="req_1",
            title="موعد Full Body",
            source_text=SOURCE,
            destination="APPOINTMENT",
            confirm=False,
        )
        assert unconfirmed["status"] == "preview"
        assert list_active_graphs(db, tenant_id="t1") == []

        first = publish_graph(
            db,
            tenant_id="t1",
            source_item_id="req_1",
            title="موعد Full Body",
            source_text=SOURCE,
            destination="APPOINTMENT",
            linked_entities=[{"type": "service", "id": "service_full_body"}],
            confirm=True,
        )
        assert first["status"] == "active"
        assert first["revision"] == 1
        definition_id = first["definition_id"]
        assert first["metering"]["is_ai"] is False
        assert first["linked_entities"] == [{"type": "service", "id": "service_full_body"}]

        same = publish_graph(
            db,
            tenant_id="t1",
            source_item_id="req_1",
            title="موعد Full Body",
            source_text=SOURCE,
            destination="APPOINTMENT",
            confirm=True,
        )
        assert same["unchanged"] is True
        assert same["revision"] == 1
        assert same["definition_id"] == definition_id

        updated = publish_graph(
            db,
            tenant_id="t1",
            source_item_id="req_1",
            title="موعد Full Body",
            source_text=SOURCE + "\nجيب الهاتف",
            destination="APPOINTMENT",
            confirm=True,
        )
        assert updated["definition_id"] == definition_id
        assert updated["revision"] == 2
        assert updated["duplicate"] is False
        keys = [row["key"] for row in updated["required_information"]]
        assert "phone" in keys
        active = get_active_graph(db, tenant_id="t1", definition_id=definition_id)
        assert active is not None
        assert active["revision"] == 2


def test_delete_removes_from_active_and_luna_tools(graph_env: None) -> None:
    with whatsapp_session(require=True) as db:
        published = publish_graph(
            db,
            tenant_id="t1",
            source_item_id="req_1",
            title="موعد Full Body",
            source_text=SOURCE,
            destination="APPOINTMENT",
            confirm=True,
        )
        definition_id = published["definition_id"]
        delete_graph(db, tenant_id="t1", definition_id=definition_id)
        assert list_active_graphs(db, tenant_id="t1") == []
        assert get_active_graph(db, tenant_id="t1", definition_id=definition_id) is None

    ctx = ToolContext(tenant_id="t1", published_revision="v1", channel="instagram")
    listed = dispatch_request_graph_tool("list_request_definitions", {}, ctx)
    assert listed["ok"] is True
    assert listed["data"]["definitions"] == []
    missing = dispatch_request_graph_tool("get_request_definition", {"definition_id": definition_id}, ctx)
    assert missing["ok"] is False


def test_tenant_isolation_and_order_destination(graph_env: None) -> None:
    with whatsapp_session(require=True) as db:
        publish_graph(
            db,
            tenant_id="t1",
            source_item_id="req_1",
            title="Order cream",
            source_text="جيب الاسم والكمية",
            destination="ORDER",
            confirm=True,
        )
        publish_graph(
            db,
            tenant_id="t2",
            source_item_id="req_1",
            title="Other tenant",
            source_text="جيب الاسم",
            destination="APPOINTMENT",
            confirm=True,
        )
        t1 = list_active_graphs(db, tenant_id="t1")
        t2 = list_active_graphs(db, tenant_id="t2")
        assert len(t1) == 1
        assert t1[0]["destination"] == "order"
        assert t1[0]["title"] != t2[0]["title"]
        other = get_active_graph(db, tenant_id="t1", definition_id=t2[0]["definition_id"])
        assert other is None
        t2_id = t2[0]["definition_id"]

    ctx = ToolContext(tenant_id="t1", published_revision="v1", channel="instagram")
    listed = dispatch_request_graph_tool("list_request_definitions", {}, ctx)
    assert listed["data"]["definitions"][0]["destination"] == "order"
    stolen = dispatch_request_graph_tool("get_request_definition", {"definition_id": t2_id}, ctx)
    assert stolen["ok"] is False


def test_sync_deletes_removed_rules(graph_env: None) -> None:
    with whatsapp_session(require=True) as db:
        sync_graphs_from_request_rules(
            db,
            tenant_id="t1",
            rules=[
                {
                    "id": "req_keep",
                    "name": "موعد",
                    "notes": "جيب الاسم والعمر",
                    "type": "APPOINTMENT",
                    "enabled": True,
                },
                {
                    "id": "req_drop",
                    "name": "طلب",
                    "notes": "جيب الاسم والكمية",
                    "type": "ORDER",
                    "enabled": True,
                },
            ],
        )
        assert {row["source_item_id"] for row in list_active_graphs(db, tenant_id="t1")} == {"req_keep", "req_drop"}
        sync_graphs_from_request_rules(
            db,
            tenant_id="t1",
            rules=[
                {
                    "id": "req_keep",
                    "name": "موعد",
                    "notes": "جيب الاسم والعمر",
                    "type": "APPOINTMENT",
                    "enabled": True,
                }
            ],
        )
        remaining = list_active_graphs(db, tenant_id="t1")
        assert [row["source_item_id"] for row in remaining] == ["req_keep"]


def test_alembic_revision_id_fits_version_num() -> None:
    from pathlib import Path

    source = Path("alembic/versions/20260820_request_graphs.py").read_text(encoding="utf-8")
    assert 'revision: str = "20260820_request_graphs"' in source
    assert len("20260820_request_graphs") <= 32
    assert 'down_revision: str | None = "20260817_web_chat_ha"' in source
