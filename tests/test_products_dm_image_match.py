"""DM inbound product image: fingerprint evidence or vision fallback; Terra still authors."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event

from db.models import Base
from db.session import reset_engine_for_tests, whatsapp_session
from services.brain.contracts.reply import FinalReplyEnvelope, OutboundMessage, TurnResult
from services.brain.contracts.turn import CustomerTurn, MediaView
from services.brain.reply.inbound_media import inbound_media_view, ingest_inbound_attachments
from services.products.image_index import find_image_candidates
from services.products.media import store_product_media
from services.products.schemas import ProductWriteBody
from services.products.service import ProductsService


@pytest.fixture()
def products_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("DASHBOARD_AUTH_SECRET", "ci-dashboard-secret")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("DISABLE_API_DOCS", "true")
    monkeypatch.setenv("LINASBOT_DATA_ROOT", str(tmp_path / "data"))
    url = f"sqlite:///{tmp_path / 'products_dm_img.db'}"
    monkeypatch.setenv("LINAS_WHATSAPP_DATABASE_URL", url)
    monkeypatch.setenv("LINAS_WHATSAPP_ALLOW_SQLITE", "true")
    reset_engine_for_tests()
    engine = create_engine(url, future=True)

    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _connection_record):  # type: ignore[no-untyped-def]
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    yield tmp_path
    reset_engine_for_tests()


@pytest.mark.asyncio
async def test_inbound_image_high_confidence_skips_vision(products_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    content = b"\xff\xd8\xff\xd9match-me"
    stored = store_product_media(
        tenant_id="tenant-dm-img",
        user_id="u1",
        filename="bag.jpg",
        content=content,
        content_type="image/jpeg",
    )
    media_id = str(stored["media_id"])
    with whatsapp_session(require=True) as session:
        svc = ProductsService(session)
        created = svc.create_product(
            tenant_id="tenant-dm-img",
            body=ProductWriteBody(
                description="brown tote",
                name="Leather Bag",
                sizes=[],
                colors=[],
                images=[{"media_id": media_id, "sort_order": 0}],
                links=[],
            ),
        )
        hits = find_image_candidates(session, tenant_id="tenant-dm-img", query_bytes=content, top_k=8)
    assert hits
    assert hits[0]["product_id"] == created["id"]

    vision = {"n": 0}

    async def _vision(*_a: object, **_k: object) -> str:
        vision["n"] += 1
        return "should-not-run"

    monkeypatch.setattr("services.brain.reply.inbound_media_enrich.describe_stills", _vision)

    async def fetch(url: str, max_bytes: int) -> dict:
        _ = url, max_bytes
        return {"ok": True, "bytes": content, "mime": "image/jpeg", "url": "https://cdn.example/a.jpg", "error": ""}

    result = await ingest_inbound_attachments(
        tenant_id="tenant-dm-img",
        attachments=[{"type": "image", "payload": {"url": "https://cdn.example/a.jpg"}}],
        fetch_url=fetch,
    )
    assert vision["n"] == 0
    assert result.product_image_matches
    assert result.product_image_matches[0]["product_id"] == created["id"]
    view = inbound_media_view(result)
    assert view["product_image_matches"][0]["product_id"] == created["id"]


@pytest.mark.asyncio
async def test_inbound_image_low_confidence_uses_vision(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "services.brain.media.product_image_match.high_confidence_matches",
        lambda *_a, **_k: [],
    )

    async def _vision(*_a: object, **_k: object) -> str:
        return "white cream jar"

    monkeypatch.setattr("services.brain.reply.inbound_media_enrich.describe_stills", _vision)
    monkeypatch.setattr("services.brain.media.describe.describe_stills", _vision)

    from services.brain.reply.inbound_media_enrich import enrich_inbound_image

    @dataclass
    class _Result:
        extract: str = ""
        product_image_matches: list = field(default_factory=list)

    result = _Result()
    parts: list[str] = []
    await enrich_inbound_image(tenant_id="t-miss", blob=b"\xff\xd8\xff\xd9nope", result=result, text_parts=parts)
    assert result.extract == "white cream jar"
    assert "white cream jar" in parts
    assert not result.product_image_matches


@pytest.mark.asyncio
async def test_image_match_evidence_still_calls_terra(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.brain import turn_pipeline as pipeline

    async def _no_confirm(*_a: object, **_k: object) -> None:
        return None

    called = {"terra": False}

    async def agentic(turn: CustomerTurn, **_k: object) -> TurnResult:
        called["terra"] = True
        assert turn.extra.get("product_image_matches")
        return TurnResult(
            stop_reason="ok",
            envelope=FinalReplyEnvelope(
                decision="reply",
                messages=[OutboundMessage(destination="instagram_dm", text="terra-authored")],
            ),
            ai_called=True,
        )

    monkeypatch.setattr(pipeline, "try_confirm_pending", _no_confirm)
    monkeypatch.setattr(pipeline, "_exact_faq_result", lambda *_a, **_k: None)

    async def no_sem(*_a: object, **_k: object) -> None:
        return None

    monkeypatch.setattr(pipeline, "_semantic_faq_result", no_sem)
    monkeypatch.setattr("services.brain.agent.loop.run_agentic_dm_path", agentic)
    turn = CustomerTurn(
        tenant_id="t1",
        conversation_id="c-img",
        media=MediaView(image_media_id="prdim_1"),
        extra={"product_image_matches": [{"product_id": "p1", "score": 0.99}], "response_language": "en"},
    )
    out = await pipeline.run_dm_after_gates(turn, message="شو هيدا؟", channel="instagram_dm")
    assert called["terra"] is True
    assert out.ai_called is True
    assert out.envelope.messages[0].text == "terra-authored"
