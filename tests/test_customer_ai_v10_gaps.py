"""Customer AI V10 remaining-gap unit tests (comment evidence, posts, dual HA, media)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from tests.cm_test_helpers import publish_test_content
from tests.customer_ai_v10_e2e_support import publish_clinic, scripted_read
from tests.customer_reply_ai_v2_helpers import _rich_sections
from tests.meta_compliance_helpers import _FakeFirestore

pytest_plugins = ("tests.customer_reply_ai_v2_fixtures", "tests.customer_ai_v10_e2e_support")


@pytest.mark.asyncio
async def test_comments_section_is_selectable(v2_env) -> None:
    await publish_test_content("t_sel", _rich_sections())
    from services.customer_reply_v2.manifest import NON_SELECTABLE_SECTIONS, build_published_manifest

    assert "comments" not in NON_SELECTABLE_SECTIONS
    _rev, sections = build_published_manifest("t_sel")
    by_id = {s.section_id: s for s in sections}
    assert by_id["comments"].selectable is True
    assert by_id["ai_basics"].selectable is False


@pytest.mark.asyncio
async def test_deterministic_comment_rules_not_in_item_index(v2_env) -> None:
    await publish_clinic("t_idx")
    from services.customer_reply_v2.manifest import get_cached_manifest
    from services.customer_reply_v2.retrieval_tools import ToolContext, dispatch_retrieval_tool

    rev, _ = get_cached_manifest("t_idx")
    ctx = ToolContext(tenant_id="t_idx", published_revision=rev, channel="instagram_comment")
    listed = dispatch_retrieval_tool("list_published_cm_items", {"section_ids": ["comments"]}, ctx)
    ids = {row["item_id"] for row in listed["data"]["items"]}
    assert "comments:rule_ai_public" in ids
    assert "comments:rule_static_dm" not in ids
    assert "comments:rule_both" not in ids


@pytest.mark.asyncio
async def test_comment_rule_does_not_block_business_read(v2_env) -> None:
    await publish_clinic("t_both")
    from services.customer_reply_v2.comment_runtime import run_customer_reply_v2_comment

    ids = ["comments:rule_ai_public", "services:svc_full_body", "branches:br_antelias"]
    out = await run_customer_reply_v2_comment(
        tenant_id="t_both",
        comment_text="قدي سعر Full Body بأنطلياس",
        detected_language="ar",
        response_language="ar",
        channel="instagram_comment",
        scripted_retrieval=scripted_read(ids),
        fixture_answer={"reply_text": "299 USD بأنطلياس", "grounding_status": "grounded"},
    )
    selected = set(out.metadata.get("selected_source_ids") or [])
    assert "comments:rule_ai_public" in selected
    assert "services:svc_full_body" in selected
    assert "branches:br_antelias" in selected


@pytest.mark.asyncio
async def test_connected_posts_rejects_foreign_account() -> None:
    from services.customer_reply_v2.connected_posts import list_connected_posts

    result = await list_connected_posts(
        tenant_id="no-such-tenant",
        platform="instagram",
        connected_account_id="ig-x",
    )
    assert result["ok"] is False
    assert result["error"] == "account_not_in_tenant"
    assert result["allow_manual_post_id"] is True


@pytest.mark.asyncio
async def test_connected_posts_graph_fetch_pagination() -> None:
    from services.customer_reply_v2.connected_posts import account_belongs_to_tenant, list_connected_posts

    async def _fetch(*, platform: str, account_id: str, after: str = "", limit: int = 25) -> list[dict[str, str]]:
        assert platform == "instagram"
        assert account_id == "ig-1"
        return [
            {
                "id": "1789",
                "preview": "hello",
                "created_time": "1",
                "permalink": "https://ig/p",
                "thumbnail": "",
                "media_type": "IMAGE",
            }
        ]

    # Injected graph_fetch still requires tenant ownership; mock belongs check via monkeypatch in caller.
    # Direct unit: graph_fetch path after ownership.
    import services.customer_reply_v2.connected_posts as cp

    orig = cp.account_belongs_to_tenant
    cp.account_belongs_to_tenant = lambda **_k: True  # type: ignore[assignment]
    try:
        result = await list_connected_posts(
            tenant_id="t1",
            platform="instagram",
            connected_account_id="ig-1",
            graph_fetch=_fetch,
        )
    finally:
        cp.account_belongs_to_tenant = orig  # type: ignore[assignment]
    assert result["ok"] is True
    assert result["posts_source"] == "graph"
    assert result["posts"][0]["id"] == "1789"
    _ = account_belongs_to_tenant


@pytest.mark.asyncio
async def test_connected_posts_graph_permission_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    from services.customer_reply_v2 import connected_posts as cp
    from services.meta_app_registry import APP_A_KEY, MetaAssetBinding, MetaBindingCredential

    binding = MetaAssetBinding(
        binding_id="b-posts",
        tenant_id="t-posts",
        channel="instagram",
        asset_id="ig-1",
        page_id="",
        instagram_account_id="ig-1",
        app_key=APP_A_KEY,
        credential_id="cred",
        status="active",
        generation=1,
        created_at=1.0,
        updated_at=1.0,
    )
    cred = MagicMock()
    cred.access_token = "token"
    monkeypatch.setattr(cp, "account_belongs_to_tenant", lambda **_k: True)
    monkeypatch.setattr(cp, "_binding_for_account", lambda **_k: binding)

    class _Reg:
        def get_credential(self, _binding):
            return cred

    monkeypatch.setattr(cp, "get_meta_app_registry", lambda: _Reg())

    async def _get(*_a, **_k):
        return httpx.Response(403, json={"error": {"code": 10, "message": "denied"}})

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_a):
            return False

        get = _get

    monkeypatch.setattr(cp.httpx, "AsyncClient", lambda **_k: _Client())
    result = await cp.list_connected_posts(tenant_id="t-posts", platform="instagram", connected_account_id="ig-1")
    assert result["ok"] is False
    assert result["error"] == "graph_permission_denied"
    assert result["allow_manual_post_id"] is True
    _ = MetaBindingCredential


@pytest.mark.asyncio
async def test_price_facts_use_validator_kind(v2_env) -> None:
    from services.customer_reply_v2.models import EvidenceRecord, RetrievalResult
    from services.customer_reply_v2.orchestrator_validate import facts_to_answer_facts

    retrieval = RetrievalResult(
        evidence=[
            EvidenceRecord(
                source_id="prices:price_full_antelias",
                section_id="prices",
                title="Full Body",
                content='{"amount": 299.0, "currency": "USD"}',
                published_revision="v1",
            ),
            EvidenceRecord(
                source_id="products:p1",
                section_id="products",
                title="Cream",
                content='{"price": "45 USD"}',
                published_revision="v1",
            ),
        ],
        evidence_status="sufficient",
        selected_source_ids=["prices:price_full_antelias", "products:p1"],
        selected_section_ids=["prices", "products"],
        rounds_used=1,
    )
    facts, _chunks = facts_to_answer_facts(retrieval)
    kinds = {row.kind for row in facts}
    assert "price" in kinds
    assert "prices" not in kinds


@pytest.mark.asyncio
async def test_comment_and_dm_live_independent_ha(monkeypatch: pytest.MonkeyPatch) -> None:
    import utils.utils
    from services.cm.comment_rules import CommentRuleDecision
    from services.meta_app_registry import APP_A_KEY, MetaAssetBinding
    from services.meta_comment_rule_both import apply_comment_and_dm_rule

    db = _FakeFirestore()
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setattr(utils.utils, "get_firestore_db", lambda: db)

    public_calls = {"n": 0}
    dm_calls = {"n": 0}

    async def public_form(*_a, **_k):
        public_calls["n"] += 1
        return True, "ok", {"id": f"pub-{public_calls['n']}"}

    async def private_reply(*_a, **_k):
        dm_calls["n"] += 1
        return True, "sent", {"message_id": f"dm-{dm_calls['n']}"}

    monkeypatch.setattr("services.meta_comment_replies._graph_post_form", public_form)
    monkeypatch.setattr("services.meta_comment_private_reply.send_comment_private_reply", private_reply)

    binding = MetaAssetBinding(
        binding_id="b-dual",
        tenant_id="t-dual",
        channel="facebook",
        asset_id="111",
        page_id="111",
        instagram_account_id="",
        app_key=APP_A_KEY,
        credential_id="c",
        status="active",
        generation=1,
        created_at=1.0,
        updated_at=1.0,
    )
    decision = CommentRuleDecision(
        action="reply_comment_and_dm",
        reply_text="public hi",
        dm_text="private hi",
        rule_id="rule_both",
        matched=True,
        rule_mode="deterministic",
    )
    event_id = "ibe_" + "c" * 40
    client = MagicMock()
    first = await apply_comment_and_dm_rule(
        rule_decision=decision,
        binding=binding,
        comment_id="cmt-1",
        simulation=False,
        capture_send=None,
        inbound_event_id=event_id,
        token="tok",
        graph_api_version="v24.0",
        client=client,
    )
    second = await apply_comment_and_dm_rule(
        rule_decision=decision,
        binding=binding,
        comment_id="cmt-1",
        simulation=False,
        capture_send=None,
        inbound_event_id=event_id,
        token="tok",
        graph_api_version="v24.0",
        client=client,
    )
    assert first.status == "sent_comment_and_dm"
    assert public_calls["n"] == 1
    assert dm_calls["n"] == 1
    assert second.status == "sent_comment_and_dm"
    _ = Any, AsyncMock
