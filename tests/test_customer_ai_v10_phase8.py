"""Customer AI V10 Phase 8 — hardening, metering reconciliation, idempotency."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, event

from tests.cm_test_helpers import publish_test_content
from tests.customer_reply_ai_v2_helpers import _rich_sections

pytest_plugins = ("tests.customer_reply_ai_v2_fixtures",)

SOURCE_FILES = [
    "services/customer_reply_v2/orchestrator.py",
    "services/customer_reply_v2/comment_runtime.py",
    "services/customer_reply_v2/answer_luna.py",
    "services/request_drafts/engine.py",
    "services/request_graphs/compiler.py",
    "services/request_graphs/service.py",
]


@pytest.fixture()
def v10_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, v2_env: Path) -> Path:
    monkeypatch.setenv("LINAS_WHATSAPP_ALLOW_SQLITE", "true")
    url = f"sqlite:///{tmp_path / 'v10_phase8.db'}"
    monkeypatch.setenv("LINAS_WHATSAPP_DATABASE_URL", url)
    from db.models import Base
    from db.session import reset_engine_for_tests

    reset_engine_for_tests()
    engine = create_engine(url, future=True)

    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _connection_record):  # type: ignore[no-untyped-def]
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    yield tmp_path
    reset_engine_for_tests()


def test_handwritten_v10_files_under_500_lines() -> None:
    root = Path(__file__).resolve().parents[1]
    for rel in SOURCE_FILES:
        lines = len((root / rel).read_text(encoding="utf-8").splitlines())
        assert lines <= 500, f"{rel} has {lines} lines"


def test_owner_ui_files_exist() -> None:
    root = Path(__file__).resolve().parents[1]
    comments = (root / "mobile/linas-ai/src/features/cm/comments/CommentsScreen.tsx").read_text(encoding="utf-8")
    assert "ResourceMetaModal" in comments
    assert (root / "mobile/linas-ai/src/features/cm/requestRules/RequestRulesScreen.tsx").is_file()
    assert (root / "mobile/linas-ai/src/features/faq/FaqResourcesEditor.tsx").is_file()
    faq_detail = (root / "mobile/linas-ai/src/features/faq/FaqDetailView.tsx").read_text(encoding="utf-8")
    assert "children" in faq_detail


def test_alembic_head_is_product_images_max5() -> None:
    from tests.test_alembic_single_head import HEAD_ID, _revisions

    revisions = _revisions()
    referenced = {parent for parents in revisions.values() for parent in parents}
    heads = [revision for revision in revisions if revision not in referenced]
    assert heads == [HEAD_ID]
    assert HEAD_ID == "20260824_prod_search_meta"


@pytest.mark.asyncio
async def test_e2e_draft_metering_no_double_ai_charge(v10_db: Path) -> None:
    from db.session import whatsapp_session
    from services.customer_reply_v2.orchestrator import run_customer_reply_v2_dm
    from services.request_drafts.engine import apply_draft_action
    from services.request_graphs.service import publish_graph

    await publish_test_content("t_e2e", _rich_sections())
    with whatsapp_session(require=True) as db:
        graph = publish_graph(
            db,
            tenant_id="t_e2e",
            source_item_id="req_e2e",
            title="موعد",
            source_text="جيب الاسم والعمر",
            destination="APPOINTMENT",
            confirm=True,
        )
        created = apply_draft_action(
            db,
            tenant_id="t_e2e",
            customer_id="u_e2e",
            action={"action": "create_draft", "definition_id": graph["definition_id"]},
        )
        draft_id = created["draft_id"]

    out = await run_customer_reply_v2_dm(
        tenant_id="t_e2e",
        message="أنا محمود، عمري 29",
        detected_language="ar",
        response_language="ar",
        channel="instagram_dm",
        provider_sender_id="u_e2e",
        conversation_id="conv_e2e",
        scripted_retrieval=[{"final_plan": {"evidence_status": "insufficient_final", "selected_source_ids": []}}],
        fixture_answer={
            "reply_text": "تمام، بقي المنطقة واليوم.",
            "grounding_status": "grounded",
            "draft_actions": [
                {
                    "action": "update_fields",
                    "draft_id": draft_id,
                    "field_updates": {"name": "محمود", "age": 29},
                }
            ],
        },
    )
    draft_result = out.metadata.get("draft_result") or {}
    assert draft_result.get("ok") is True
    values = (draft_result.get("results") or [{}])[0].get("values") or {}
    assert values.get("name") == "محمود"
    assert values.get("age") == 29
    metering = out.metadata.get("metering") or {}
    rows = list(metering.get("invocations") or [])
    ai_rows = [row for row in rows if row.get("is_ai")]
    draft_rows = [row for row in rows if row["operation"] == "draft_storage"]
    assert draft_rows
    assert draft_rows[0]["is_ai"] is False
    assert metering["ai_invocation_count"] == len(ai_rows)
    assert any(row["operation"] == "luna_retrieval" for row in ai_rows)
    assert any(str(row["operation"]).startswith("tera_") for row in ai_rows)
    assert out.metadata.get("classic_fallback") is False


def test_duplicate_webhook_does_not_double_update(v10_db: Path) -> None:
    from db.session import whatsapp_session
    from services.request_drafts.engine import apply_draft_action
    from services.request_graphs.service import publish_graph

    with whatsapp_session(require=True) as db:
        graph = publish_graph(
            db,
            tenant_id="t_dup",
            source_item_id="req_dup",
            title="موعد",
            source_text="جيب الاسم",
            destination="APPOINTMENT",
            confirm=True,
        )
        created = apply_draft_action(
            db,
            tenant_id="t_dup",
            customer_id="u_dup",
            action={"action": "create_draft", "definition_id": graph["definition_id"]},
        )
        action = {
            "action": "update_fields",
            "draft_id": created["draft_id"],
            "field_updates": {"name": "محمود"},
        }
        first = apply_draft_action(db, tenant_id="t_dup", customer_id="u_dup", action=action)
        second = apply_draft_action(db, tenant_id="t_dup", customer_id="u_dup", action=action)
        assert first["ok"] is True
        assert second["unchanged"] is True
        assert second["values"]["name"] == "محمود"


def test_concurrent_updates_on_separate_drafts(v10_db: Path) -> None:
    from db.session import whatsapp_session
    from services.request_drafts.engine import apply_draft_action
    from services.request_graphs.service import publish_graph

    with whatsapp_session(require=True) as db:
        appt = publish_graph(
            db,
            tenant_id="t_cc",
            source_item_id="req_a",
            title="موعد",
            source_text="جيب الاسم",
            destination="APPOINTMENT",
            confirm=True,
        )
        order = publish_graph(
            db,
            tenant_id="t_cc",
            source_item_id="req_o",
            title="طلب",
            source_text="جيب الاسم والكمية",
            destination="ORDER",
            confirm=True,
        )
        d1 = apply_draft_action(
            db,
            tenant_id="t_cc",
            customer_id="u_cc",
            action={"action": "create_draft", "definition_id": appt["definition_id"]},
        )
        d2 = apply_draft_action(
            db,
            tenant_id="t_cc",
            customer_id="u_cc",
            action={"action": "create_draft", "definition_id": order["definition_id"]},
        )
        apply_draft_action(
            db,
            tenant_id="t_cc",
            customer_id="u_cc",
            action={"action": "update_fields", "draft_id": d1["draft_id"], "field_updates": {"name": "A"}},
        )
        apply_draft_action(
            db,
            tenant_id="t_cc",
            customer_id="u_cc",
            action={"action": "update_fields", "draft_id": d2["draft_id"], "field_updates": {"quantity": 2}},
        )
    from services.customer_reply_v2.open_drafts import list_open_collecting_drafts

    rows = {row["draft_id"]: row for row in list_open_collecting_drafts(tenant_id="t_cc", customer_id="u_cc")}
    assert rows[d1["draft_id"]]["values"]["name"] == "A"
    assert rows[d2["draft_id"]]["values"]["quantity"] == 2


def test_titles_payload_reports_no_silent_truncation() -> None:
    from services.customer_reply_v2.operational_titles import collect_operational_titles, inline_titles_for_luna

    sections = {"services": {"items": [{"id": f"s{i}", "name": f"Service {i}", "enabled": True} for i in range(120)]}}
    titles = collect_operational_titles(sections)
    payload = inline_titles_for_luna(titles)
    assert payload["operational_title_count"] == 120
    assert payload["operational_titles_truncated"] is False
    assert payload["operational_titles_has_more"] is True


def test_faq_and_comment_rule_metering_not_ai() -> None:
    from services.customer_reply_v2.invocation_meter import CustomerTurnMeter, InvocationRecord
    from services.customer_reply_v2.orchestrator_faq import faq_direct_invocation

    meter = CustomerTurnMeter(tenant_id="t_meter")
    meter.record(faq_direct_invocation())
    meter.record(InvocationRecord(operation="comment_rule_deterministic", provider="none", is_ai=False, success=True))
    public = meter.to_public_dict()
    assert public["ai_invocation_count"] == 0
    assert all(not row["is_ai"] for row in public["invocations"])
