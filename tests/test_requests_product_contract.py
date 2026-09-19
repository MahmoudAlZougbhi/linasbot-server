"""Requests product contract: dead island gone, HUMAN→Live Chat, persistable types."""

from __future__ import annotations

from inspect import getsource
from pathlib import Path
from types import SimpleNamespace

import pytest

from services.brain.actions.requests import persist_request
from services.brain.contracts.actions import ActionProposal
from services.brain.planner.heuristic import plan_message
from services.requests.constants import PERSISTABLE_REQUEST_TYPES, REQUEST_TYPES
from services.requests.schemas import RequestCreateBody
from services.requests.service import CustomerRequestsError, CustomerRequestsService
from services.requests.state_machine import can_transition
from services.requests.status_ui import status_bucket, status_label

ROOT = Path(__file__).resolve().parents[1]
DEAD_CAPTURE = (
    "services/requests/ai_tool.py",
    "services/requests/capture_answer_loop.py",
    "services/requests/capture_tools_wire.py",
    "services/requests/intent.py",
)
REQUEST_ROUTES = (
    "/api/requests/setup-status",
    "/api/requests",
    "/api/requests/{request_id}",
    "/assign",
    "/notes",
    "/status",
    "/final-action",
    "/notify-retry",
    "/manual-mode/resume",
    "/manual-chat/send",
)
GRAPH_ROUTES = (
    "/api/cm/request-graphs/preview",
    "/api/cm/request-graphs/publish",
    "/api/cm/request-graphs",
    "/api/cm/request-graphs/delete",
)


def test_dead_capture_island_is_gone() -> None:
    for rel in DEAD_CAPTURE:
        assert not (ROOT / rel).exists(), rel
    for path in (ROOT / "services/requests").rglob("*.py"):
        src = path.read_text(encoding="utf-8")
        assert "capture_answer_loop" not in src
        assert "capture_tools_wire" not in src
        assert "from services.requests.intent" not in src
        assert "from services.requests.ai_tool" not in src


def test_persistable_types_exclude_human() -> None:
    assert REQUEST_TYPES == ("ORDER", "APPOINTMENT", "OTHER", "HUMAN")
    assert PERSISTABLE_REQUEST_TYPES == ("ORDER", "APPOINTMENT", "OTHER")
    assert "HUMAN" not in PERSISTABLE_REQUEST_TYPES
    assert can_transition("HUMAN", "NEW", "IN_REVIEW") is False


def test_status_ui_buckets_match_mobile() -> None:
    assert status_bucket("NEW") == "new"
    assert status_bucket("IN_REVIEW") == "in_progress"
    assert status_bucket("WAITING_FOR_CUSTOMER") == "in_progress"
    assert status_bucket("CONFIRMED") == "in_progress"
    assert status_bucket("READY") == "in_progress"
    assert status_bucket("COMPLETED") == "done"
    assert status_bucket("CANCELLED") == "cancelled"
    assert status_label("READY") == "In Progress"
    assert status_label("COMPLETED") == "Done"


def test_http_contracts_preserved() -> None:
    api = Path("modules/requests_api.py").read_text(encoding="utf-8")
    graphs = Path("modules/cm_request_graphs_api.py").read_text(encoding="utf-8")
    for route in REQUEST_ROUTES:
        assert route in api, route
    for route in GRAPH_ROUTES:
        assert route in graphs, route


def test_persist_request_source_has_no_message_charge() -> None:
    src = getsource(persist_request)
    assert "message_ledger" not in src
    assert "credit_ledger" not in src
    assert "reserve(" not in src


def test_hours_question_is_not_an_order() -> None:
    types = {task.type for task in plan_message("what are your opening hours?").tasks}
    assert "hours" in types
    assert "product_request" not in types
    assert "service_request" not in types


def test_human_intent_is_not_an_order() -> None:
    types = {task.type for task in plan_message("Can I speak to someone?").tasks}
    assert "human_request" in types
    assert "product_request" not in types


def test_live_chat_draft_submit_does_not_create_a_request(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.requests.request_drafts import engine as draft_engine

    created: list[dict] = []

    def _create(snapshot: dict) -> dict:
        created.append(snapshot)
        return {"ok": True, "request_id": "should-not-exist"}

    monkeypatch.setattr(
        draft_engine,
        "_load_graph",
        lambda session, tenant_id, definition_id: {"required_information": [], "confirmation_required": False},
    )
    row = SimpleNamespace(
        destination="live_chat",
        status="ready",
        values_json={},
        missing_json=[],
        items_json=[],
        linked_entities_json=[],
        submitted_request_id=None,
        definition_id="def-human",
        tenant_id="t1",
        draft_id="draft_1",
        customer_id="c1",
        definition_revision=1,
        created_at=None,
        updated_at=None,
    )
    result = draft_engine._submit(None, row, {"confirmed": True}, create_request_fn=_create)
    assert result["ok"] is True
    assert result["request_type"] == "HUMAN"
    assert result["route"] == "live_chat"
    assert result["persisted"] is False
    assert created == []
    assert row.submitted_request_id is None


def test_create_from_ai_rejects_human() -> None:
    svc = CustomerRequestsService(object())  # type: ignore[arg-type]
    body = RequestCreateBody(
        request_type="HUMAN",
        source_channel="instagram_dm",
        customer_confirmed=True,
        idempotency_key="idem-human-001",
        title="Speak to staff",
    )
    with pytest.raises(CustomerRequestsError) as exc:
        svc.create_from_ai(tenant_id="tenant-a", body=body)
    assert exc.value.code == "HUMAN_ROUTES_TO_LIVE_CHAT"


def test_persist_request_rejects_human() -> None:
    receipt = persist_request(
        session=object(),
        tenant_id="t1",
        proposal=ActionProposal(
            task_id="h1",
            action_type="start_request",
            expected_revision="1",
            confirmation_message_id="m1",
            fields={"request_type": "HUMAN", "confirmation_text": "yes"},
        ),
        channel="instagram_dm",
        customer_id="c1",
        conversation_id="conv-1",
        message_id="m1",
        customer_text="yes",
        current_revision="1",
    )
    assert receipt.state == "rejected"
    assert receipt.reason == "human_routes_to_live_chat"
