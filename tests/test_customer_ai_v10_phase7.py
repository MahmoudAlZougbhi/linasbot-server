"""Customer AI V10 Phase 7 — Dynamic Draft engine."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event

from db.models import Base
from db.session import reset_engine_for_tests, whatsapp_session
from services.customer_reply_v2.draft_actions import plan_drafts_for_turn
from services.customer_reply_v2.open_drafts import has_open_collecting_draft, list_open_collecting_drafts
from services.request_drafts.engine import apply_draft_action, apply_draft_actions
from services.request_graphs.service import delete_graph, publish_graph

SOURCE = "موعد Full Body\nجيب الاسم والعمر والطول والوزن والمنطقة واليوم المطلوب."
ORDER_SOURCE = "طلب كريم\nجيب الاسم والكمية"


@pytest.fixture()
def draft_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("LINAS_WHATSAPP_ALLOW_SQLITE", "true")
    monkeypatch.setenv("CUSTOMER_AI_V10_RUNTIME", "true")
    url = f"sqlite:///{tmp_path / 'drafts.db'}"
    monkeypatch.setenv("LINAS_WHATSAPP_DATABASE_URL", url)
    reset_engine_for_tests()
    engine = create_engine(url, future=True)

    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _connection_record):  # type: ignore[no-untyped-def]
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    yield
    reset_engine_for_tests()


def _publish(db, *, tenant: str = "t1", source_id: str = "req_1", text: str = SOURCE, dest: str = "APPOINTMENT"):
    return publish_graph(
        db,
        tenant_id=tenant,
        source_item_id=source_id,
        title="موعد Full Body" if dest == "APPOINTMENT" else "Order",
        source_text=text,
        destination=dest,
        confirm=True,
    )


def test_one_message_collects_fields_and_rejects_invented_keys(draft_env: None) -> None:
    with whatsapp_session(require=True) as db:
        graph = _publish(db)
        created = apply_draft_action(
            db,
            tenant_id="t1",
            customer_id="cust_1",
            action={"action": "create_draft", "definition_id": graph["definition_id"]},
        )
        assert created["ok"] is True
        draft_id = created["draft_id"]
        updated = apply_draft_action(
            db,
            tenant_id="t1",
            customer_id="cust_1",
            action={
                "action": "update_fields",
                "draft_id": draft_id,
                "field_updates": {
                    "name": "محمود",
                    "age": 29,
                    "height": 181,
                    "weight": 82,
                    "national_id": "x",
                },
            },
        )
        assert updated["ok"] is True
        assert updated["values"]["height"] == 181
        assert "national_id" not in updated["values"]
        assert any(row["reason"] == "unknown_field" for row in updated["rejected_fields"])
        assert "area" in updated["missing_fields"]
        assert updated["ready_to_submit"] is False
        blocked = apply_draft_action(
            db,
            tenant_id="t1",
            customer_id="cust_1",
            action={"action": "submit", "draft_id": draft_id, "confirmed": True},
        )
        assert blocked["error"] == "incomplete_submission"


def test_multiple_drafts_shared_facts_add_replace_pause_resume(draft_env: None) -> None:
    with whatsapp_session(require=True) as db:
        appt = _publish(db, source_id="req_a")
        order = _publish(db, source_id="req_o", text=ORDER_SOURCE, dest="ORDER")
        first = apply_draft_action(
            db,
            tenant_id="t1",
            customer_id="cust_1",
            action={"action": "create_draft", "definition_id": appt["definition_id"]},
        )
        apply_draft_action(
            db,
            tenant_id="t1",
            customer_id="cust_1",
            action={
                "action": "update_fields",
                "draft_id": first["draft_id"],
                "field_updates": {"name": "محمود"},
            },
        )
        second = apply_draft_action(
            db,
            tenant_id="t1",
            customer_id="cust_1",
            action={"action": "create_draft", "definition_id": order["definition_id"]},
        )
        assert second["values"]["name"] == "محمود"
        apply_draft_action(
            db,
            tenant_id="t1",
            customer_id="cust_1",
            action={
                "action": "add_item",
                "draft_id": first["draft_id"],
                "item": {"type": "service", "id": "underarms"},
            },
        )
        replaced = apply_draft_action(
            db,
            tenant_id="t1",
            customer_id="cust_1",
            action={
                "action": "replace_item",
                "draft_id": first["draft_id"],
                "from_item": {"type": "service", "id": "underarms"},
                "to_item": {"type": "service", "id": "bikini"},
            },
        )
        assert [item["id"] for item in replaced["items"]] == ["bikini"]
        paused = apply_draft_action(
            db,
            tenant_id="t1",
            customer_id="cust_1",
            action={"action": "pause", "draft_id": first["draft_id"]},
        )
        assert paused["status"] == "paused"
        resumed = apply_draft_action(
            db,
            tenant_id="t1",
            customer_id="cust_1",
            action={"action": "resume", "draft_id": first["draft_id"]},
        )
        assert resumed["status"] == "collecting"
    assert has_open_collecting_draft(tenant_id="t1", customer_id="cust_1") is True
    assert len(list_open_collecting_drafts(tenant_id="t1", customer_id="cust_1")) == 2


def test_submit_requires_confirmation_and_is_idempotent(draft_env: None) -> None:
    with whatsapp_session(require=True) as db:
        graph = _publish(db, text="جيب الاسم")
        created = apply_draft_action(
            db,
            tenant_id="t1",
            customer_id="cust_1",
            action={"action": "create_draft", "definition_id": graph["definition_id"]},
        )
        apply_draft_action(
            db,
            tenant_id="t1",
            customer_id="cust_1",
            action={"action": "update_fields", "draft_id": created["draft_id"], "field_updates": {"name": "محمود"}},
        )
        need_confirm = apply_draft_action(
            db,
            tenant_id="t1",
            customer_id="cust_1",
            action={"action": "submit", "draft_id": created["draft_id"]},
        )
        assert need_confirm["error"] == "confirmation_required"
        created_ids: list[str] = []

        def _create(snapshot):
            created_ids.append(snapshot["draft_id"])
            return {"ok": True, "request_id": "req_row_1"}

        submitted = apply_draft_action(
            db,
            tenant_id="t1",
            customer_id="cust_1",
            action={"action": "submit", "draft_id": created["draft_id"], "confirmed": True},
            create_request_fn=_create,
        )
        assert submitted["status"] == "submitted"
        assert submitted["pending_confirmation"] is True
        assert "غير مؤكد" in submitted["customer_message_hint"]
        again = apply_draft_action(
            db,
            tenant_id="t1",
            customer_id="cust_1",
            action={"action": "submit", "draft_id": created["draft_id"], "confirmed": True},
            create_request_fn=_create,
        )
        assert again["unchanged"] is True
        assert created_ids == [created["draft_id"]]


def test_graph_revision_and_delete_while_open(draft_env: None) -> None:
    with whatsapp_session(require=True) as db:
        graph = _publish(db, text="جيب الاسم")
        created = apply_draft_action(
            db,
            tenant_id="t1",
            customer_id="cust_1",
            action={"action": "create_draft", "definition_id": graph["definition_id"]},
        )
        apply_draft_action(
            db,
            tenant_id="t1",
            customer_id="cust_1",
            action={"action": "update_fields", "draft_id": created["draft_id"], "field_updates": {"name": "محمود"}},
        )
        publish_graph(
            db,
            tenant_id="t1",
            source_item_id="req_1",
            title="موعد Full Body",
            source_text="جيب الاسم والعمر",
            destination="APPOINTMENT",
            confirm=True,
        )
        updated = apply_draft_action(
            db,
            tenant_id="t1",
            customer_id="cust_1",
            action={"action": "update_fields", "draft_id": created["draft_id"], "field_updates": {"age": 29}},
        )
        assert updated["warning"] == "graph_revision_migrated"
        assert updated["values"]["name"] == "محمود"
        assert updated["values"]["age"] == 29
        delete_graph(db, tenant_id="t1", definition_id=graph["definition_id"])
        gone = apply_draft_action(
            db,
            tenant_id="t1",
            customer_id="cust_1",
            action={"action": "update_fields", "draft_id": created["draft_id"], "field_updates": {"name": "x"}},
        )
        assert gone["error"] == "definition_deleted"
    assert has_open_collecting_draft(tenant_id="t1", customer_id="cust_1") is False


def test_tenant_isolation_and_public_comment_refused(draft_env: None) -> None:
    with whatsapp_session(require=True) as db:
        graph = _publish(db, text="جيب الاسم")
        mine = apply_draft_action(
            db,
            tenant_id="t1",
            customer_id="cust_1",
            action={"action": "create_draft", "definition_id": graph["definition_id"]},
        )
        stolen = apply_draft_action(
            db,
            tenant_id="t1",
            customer_id="cust_other",
            action={"action": "update_fields", "draft_id": mine["draft_id"], "field_updates": {"name": "nope"}},
        )
        assert stolen["error"] == "draft_not_found"
        other_tenant = apply_draft_action(
            db,
            tenant_id="t2",
            customer_id="cust_1",
            action={"action": "create_draft", "definition_id": graph["definition_id"]},
        )
        assert other_tenant["error"] == "definition_not_found"

    class Answer:
        draft_actions = [{"action": "create_draft", "definition_id": "x"}]
        raw_structured = {}
        request_actions = []

    public = plan_drafts_for_turn(
        tenant_id="t1",
        customer_id="cust_1",
        channel="instagram_comment",
        answer=Answer(),
        is_public=True,
    )
    assert public["draft_result"]["error"] == "public_comment_refused"
    assert public["draft_result"]["is_ai"] is False


def test_cancel_and_batch_actions(draft_env: None) -> None:
    with whatsapp_session(require=True) as db:
        graph = _publish(db, text="جيب الاسم")
        created = apply_draft_action(
            db,
            tenant_id="t1",
            customer_id="cust_1",
            action={"action": "create_draft", "definition_id": graph["definition_id"]},
        )
        batch = apply_draft_actions(
            db,
            tenant_id="t1",
            customer_id="cust_1",
            actions=[
                {"action": "update_fields", "draft_id": created["draft_id"], "field_updates": {"name": "محمود"}},
                {"action": "cancel", "draft_id": created["draft_id"]},
            ],
        )
        assert batch["ok"] is True
        assert batch["results"][-1]["status"] == "cancelled"
        assert batch["is_ai"] is False


def test_open_draft_sets_faq_guard(draft_env: None) -> None:
    from services.customer_reply_v2.orchestrator_faq import build_faq_guards

    with whatsapp_session(require=True) as db:
        graph = _publish(db, text="جيب الاسم")
        apply_draft_action(
            db,
            tenant_id="t1",
            customer_id="cust_1",
            action={"action": "create_draft", "definition_id": graph["definition_id"]},
        )
    guards = build_faq_guards(
        tenant_id="t1",
        customer_id="cust_1",
        channel="instagram_dm",
        attachment_types=None,
        reply_to="",
        has_unresolved_context_refs=False,
    )
    assert guards.has_open_draft is True
