"""P07 fixes. New behavior stays off unless the matching flag is on."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from services.billing.membership.daily_edits import (
    commit_edit,
    operation_id,
    payload_hash,
    reserve_edit,
    reset_daily_edits_for_tests,
    status,
)
from services.billing.membership.delete_budget import reset_delete_budget_for_tests
from services.billing.membership.edit_classify import classify_section_change
from services.billing.membership.edit_http import guarded_cm_write, is_free_edit
from services.brain.actions.pending import attach_confirmation, try_confirm_pending
from services.brain.contracts.actions import ActionProposal, ActionProposalSet
from services.brain.contracts.turn import CustomerTurn
from services.brain.conversation_store import reset_conversation_store_for_tests
from services.brain.reply.price_grounding import grounded_price
from services.brain.reply.retrieval_item_index import section_item_cap
from services.brain.search.index_keep import index_reply_mode
from services.products.import_receipts import reset_import_receipts_for_tests
from services.products.search_match import match_products, media_facts
from services.requests.draft_ttl import draft_is_expired, draft_ttl_days
from services.requests.memory_dates import absolute_weekday, date_needs_refresh, missing_request_fields
from services.requests.routing import route_assignee
from services.requests.webchat_notify import notices, reset_notices_for_tests


def _on(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    monkeypatch.setenv(f"LINAS_FLAG_{name.upper()}", "on")


@pytest.fixture(autouse=True)
def _clean() -> None:
    reset_conversation_store_for_tests()
    reset_daily_edits_for_tests()
    reset_delete_budget_for_tests()
    reset_import_receipts_for_tests()
    reset_notices_for_tests()


def _stage(kind: str) -> CustomerTurn:
    turn = CustomerTurn(tenant_id="t1", conversation_id=f"c-{kind}", event_ids=["m1"])
    attach_confirmation(
        turn,
        ActionProposalSet(
            actions=[
                ActionProposal(
                    task_id="t",
                    action_type="start_request",
                    fields={"request_type": kind, "collected_fields": {"name": "Sara"}},
                )
            ]
        ),
    )
    return turn


@pytest.mark.asyncio
async def test_yes_does_not_submit_until_the_flag_is_on(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    async def fake_execute(turn, proposals, message):
        _ = (turn, proposals, message)
        calls["n"] += 1
        return [{"action_type": "submit_request", "state": "success", "backend_id": "req1"}]

    monkeypatch.setattr("services.brain.actions.pending._execute", fake_execute)
    turn = _stage("APPOINTMENT")
    assert await try_confirm_pending(turn, "yes confirm send it", "web_chat") is None
    assert calls["n"] == 0
    _on(monkeypatch, "request_confirm")
    assert await try_confirm_pending(turn, "book tomorrow", "web_chat") is None
    assert calls["n"] == 0
    for phrase in ("yes confirm send it", "تمام", "oui", "eh akid"):
        staged = _stage("ORDER" if phrase == "oui" else "APPOINTMENT")
        assert await try_confirm_pending(staged, phrase, "web_chat") is None
    assert calls["n"] == 4
    again = CustomerTurn(tenant_id="t1", conversation_id="c-APPOINTMENT", event_ids=["m2"])
    assert await try_confirm_pending(again, "yes", "web_chat") is None
    assert calls["n"] == 4


def test_free_deletes_do_not_spend_edits(monkeypatch: pytest.MonkeyPatch) -> None:
    assert is_free_edit("product:delete") is False
    _on(monkeypatch, "free_deletes")
    assert is_free_edit("product:delete") is True
    assert is_free_edit("faq:archive", safety=True) is True
    current = {"items": [{"id": "a", "name": "A"}, {"id": "b", "name": "B"}]}
    deleted = {"items": [{"id": "a", "name": "A"}]}
    edited = {"items": [{"id": "a", "name": "A2"}]}
    assert classify_section_change("knowledge", current, current) == "noop"
    assert classify_section_change("knowledge", current, deleted) == "delete_only"
    assert classify_section_change("knowledge", current, edited) == "billable"
    op = operation_id(tenant_id="t1", kind="seed", payload_hash=payload_hash({"n": 1}))
    reserve_edit(tenant_id="t1", operation_id=op)
    commit_edit(tenant_id="t1", operation_id=op)
    with guarded_cm_write(tenant_id="t1", section="knowledge", current=current, payload=deleted) as edit_op:
        assert edit_op is None
    assert status("t1").used == 1


def test_bulk_delete_reports_other_tenant_as_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.products.service import ProductsService

    _on(monkeypatch, "free_deletes")
    monkeypatch.setattr("services.products.service.remove_product_from_index", lambda *a, **k: None)
    monkeypatch.setattr("services.products.service.clear_context_for_product", lambda *a, **k: None)
    monkeypatch.setattr("services.products.service.clear_reply_for_product", lambda *a, **k: None)
    rows = {("t", "p1"): SimpleNamespace(id="p1")}

    class Repo:
        def get_product(self, *, tenant_id: str, product_id: str):
            return rows.get((tenant_id, product_id))

        def delete_product(self, row):
            rows.pop(("t", row.id), None)
            return []

    svc = ProductsService.__new__(ProductsService)
    svc.repo = Repo()
    svc.session = SimpleNamespace()
    svc._invalidate_customer_ai_products = lambda *a, **k: None
    before = status("t").used
    results = svc.bulk_delete(tenant_id="t", ids=["p1", "other"])
    assert results[0]["deleted"] is True
    assert results[1]["error"] == "NOT_FOUND"
    assert status("t").used == before


def test_import_retry_does_not_create_twice(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.products.import_service import import_csv_rows

    _on(monkeypatch, "import_idempotent")
    calls = {"n": 0}

    class Svc:
        def create_product(self, **kwargs):
            _ = kwargs
            calls["n"] += 1
            return {}

    csv_text = "name,price\nAftercare Serum,29\n"
    first = import_csv_rows(Svc(), tenant_id="t", csv_text=csv_text)
    second = import_csv_rows(Svc(), tenant_id="t", csv_text=csv_text)
    assert first["created"] == 1
    assert second.get("replayed") is True
    assert calls["n"] == 1


def test_draft_ttl_and_memory() -> None:
    now = datetime(2026, 10, 9, tzinfo=UTC)
    assert draft_ttl_days(3) == 0
    assert draft_is_expired(now - timedelta(days=40), now=now) is False


def test_draft_ttl_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    _on(monkeypatch, "draft_ttl")
    now = datetime(2026, 10, 9, tzinfo=UTC)
    assert draft_ttl_days(3) == 7
    assert draft_ttl_days(None) == 30
    assert draft_is_expired(now - timedelta(days=31), now=now) is True
    assert draft_is_expired(now - timedelta(days=10), now=now) is False
    saturday = absolute_weekday("next Saturday", today=now.date())
    assert saturday is not None and saturday.weekday() == 5 and saturday > now.date()
    assert date_needs_refresh(saturday, today=saturday + timedelta(days=1)) is True
    missing = missing_request_fields(
        ["name", "age", "service", "body_parts", "preferred_date", "branch"],
        {"name": "Sara", "service": "laser", "branch": "A"},
    )
    assert missing == ["age", "body_parts", "preferred_date"]


def test_routing_and_prices() -> None:
    rules = [
        {"branch": "A", "assignee": "staff-x"},
        {"branch": "B", "assignee": "staff-y"},
    ]
    assert route_assignee(rules, branch="A", owner_id="owner") == "staff-x"
    assert route_assignee(rules, branch="C", owner_id="owner") == "owner"
    assert grounded_price(asked="full body laser", title="full body laser", price="$120") == "$120"
    assert grounded_price(asked="full body laser", title="face laser", price="$40") is None
    assert grounded_price(asked="full body laser", title="full body laser", price="$40", placeholder=True) is None


def test_product_search_and_media() -> None:
    products = [
        {
            "name": "Aftercare Serum",
            "price": "$29",
            "aliases": ["سيروم العناية"],
            "links": ["https://shop.example/serum", "https://tiktok.example/serum"],
        }
    ]
    for query in (
        "Aftercare Serum price",
        "aftercare",
        "aftreacre serom",
        "سيروم العناية",
        "fi 3andkon aftercare serum",
    ):
        hits = match_products(query, products)
        assert hits and hits[0]["name"] == "Aftercare Serum"
    facts = media_facts(
        [
            {"type": "image", "url": "https://cdn.example/a.jpg"},
            {"type": "link", "url": "https://tiktok.example/serum"},
        ]
    )
    assert facts["video"] == []
    assert "https://cdn.example/a.jpg" in facts["image"]
    invented = "https://evil.example/nope"
    assert invented not in facts["image"] + facts["video"] + facts["link"]


def test_caps_and_channels(monkeypatch: pytest.MonkeyPatch) -> None:
    assert section_item_cap() == 80
    monkeypatch.setenv("LINAS_FLAG_RETRIEVAL_ITEM_CAP", "200")
    assert section_item_cap() == 200
    assert index_reply_mode(has_previous=True, refresh_failed=True) == "previous"
    assert index_reply_mode(has_previous=False, refresh_failed=True) == "closed"


@pytest.mark.asyncio
async def test_web_chat_notice_and_handoff(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.brain.actions.handoff import escalate_to_human
    from services.brain.contracts.actions import ActionProposal
    from services.requests.delivery import deliver_on_source_channel

    failed = await deliver_on_source_channel(
        tenant_id="t",
        channel="web_chat",
        source_account_id=None,
        external_customer_id=None,
        conversation_id="c",
        text="ready",
    )
    assert failed.status == "failed"
    _on(monkeypatch, "webchat_notify")
    sent = await deliver_on_source_channel(
        tenant_id="t",
        channel="web_chat",
        source_account_id=None,
        external_customer_id=None,
        conversation_id="c",
        text="ready",
    )
    assert sent.status == "sent"
    assert notices()[0]["role"] == "assistant"

    async def no_target(*args, **kwargs):
        _ = (args, kwargs)
        return None

    monkeypatch.setattr("utils.utils_takeover.set_human_takeover_status", no_target)
    proposal = ActionProposal(task_id="h", action_type="escalate_to_human")
    unknown = await escalate_to_human(proposal=proposal, user_id="u", conversation_id="c")
    assert unknown.state == "unknown"
    _on(monkeypatch, "handoff_fallback")
    done = await escalate_to_human(proposal=proposal, user_id="u", conversation_id="c")
    assert done.state == "success"


def test_reply_language_uses_the_session_when_detection_is_empty() -> None:
    from services.ai_setup.language_policy import choose_reply_language

    assert choose_reply_language(detected="en", session_language="ar") == "en"
    assert choose_reply_language(detected="franco", session_language="en") == "ar"
    assert choose_reply_language(detected="", session_language="en") == "en"


def test_assignee_must_be_a_member(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.requests.assignees import assert_assignee
    from services.requests.service import CustomerRequestsError, CustomerRequestsService

    monkeypatch.setattr("services.requests.assignees.assignee_is_member", lambda tenant, user: user == "staff")
    with pytest.raises(CustomerRequestsError) as exc:
        assert_assignee("t", "000")
    assert exc.value.code == "ASSIGNEE_NOT_MEMBER"
    row = SimpleNamespace(assigned_user_id=None, row_version=1)
    svc = CustomerRequestsService.__new__(CustomerRequestsService)
    svc._lock_version = lambda *a, **k: row
    svc.repo = SimpleNamespace(add_event=lambda **k: None)
    svc.session = SimpleNamespace(commit=lambda: None)
    monkeypatch.setattr("services.requests.service.serialize_request", lambda item: {"id": item.assigned_user_id})
    svc.assign(tenant_id="t", request_id="r", actor_user_id="owner", assigned_user_id="000", row_version=1)
    assert row.assigned_user_id == "000"
    row.row_version = 1
    _on(monkeypatch, "assignee_check")
    with pytest.raises(CustomerRequestsError):
        svc.assign(tenant_id="t", request_id="r", actor_user_id="owner", assigned_user_id="000", row_version=1)


def test_repeat_embed_uses_the_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    from services.owner_portal.embed_cache import reset_embed_cache_for_tests
    from services.owner_portal.embed_queue import pending, reset_embed_queue_for_tests
    from services.owner_portal.owner_embed import embed_batch

    reset_embed_cache_for_tests()
    reset_embed_queue_for_tests()
    _on(monkeypatch, "voyage_cache")
    monkeypatch.setattr("services.owner_portal.owner_embed.voyage_api_key", lambda: "test-key")
    calls = {"n": 0}

    class Response:
        status_code = 200
        headers: dict[str, str] = {}

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"data": [{"embedding": [0.2, 0.3]}]}

    def post(*args, **kwargs):
        _ = (args, kwargs)
        calls["n"] += 1
        return Response()

    monkeypatch.setattr(httpx, "post", post)
    embed_batch(["same text"], query=False)
    embed_batch(["same text"], query=False)
    assert calls["n"] == 1
    _on(monkeypatch, "voyage_retry")

    def boom(*args, **kwargs):
        _ = (args, kwargs)
        raise RuntimeError("429")

    monkeypatch.setattr(httpx, "post", boom)
    embed_batch(["other text"], query=False)
    assert pending()[0]["state"] == "pending"


@pytest.mark.asyncio
async def test_missing_zh_can_be_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.brain.language_detection_service import LanguageDetectionService

    class Message:
        content = '{"en": {"question": "q", "answer": "a"}}'

    class Choice:
        message = Message()

    class Response:
        choices = [Choice()]

    captured: dict[str, str] = {}

    async def create(**kwargs):
        captured["prompt"] = kwargs["messages"][0]["content"]
        return Response()

    monkeypatch.setattr(
        "services.brain.language_detection_service.openai_client.chat.completions.create",
        create,
    )
    service = LanguageDetectionService()
    blocked = await service.translate_training_pair(
        question="How much?",
        answer="120",
        source_language="en",
        target_languages=["en", "zh"],
    )
    assert blocked["success"] is False
    assert "zh" in blocked["missing_languages"]
    assert '"zh"' in captured["prompt"]
    _on(monkeypatch, "faq_skip_missing")
    allowed = await service.translate_training_pair(
        question="How much?",
        answer="120",
        source_language="en",
        target_languages=["en", "zh"],
    )
    assert allowed["success"] is True
    assert allowed["translations"]["en"]["answer"] == "120"
