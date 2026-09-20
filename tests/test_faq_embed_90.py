"""FAQ question embed ≥ 0.90 returns the published answer with zero generation."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pytest

from services.brain.contracts.reply import FinalReplyEnvelope, OutboundMessage, TurnResult
from services.brain.contracts.turn import CustomerTurn, HistorySnapshot
from services.brain.faq_embed import FAQ_COSINE_MIN, pick_faq_embed_winner
from services.brain.providers.spaces import ENTITY_DOCUMENT
from services.brain.search.store import StoreHit, reset_memory_store, write_documents
from tests.cm_test_helpers import publish_pointer_content

pytest_plugins = ("tests.customer_reply_ai_v2_fixtures",)

ROOT = Path(__file__).resolve().parents[1]
ANSWER = "Twenty dollars, published verbatim."
QUESTION = "What is the laser session price?"


def _pair(score: float) -> tuple[list[float], list[float]]:
    clamped = min(max(score, -1.0), 1.0)
    return [1.0, 0.0], [clamped, math.sqrt(max(0.0, 1.0 - clamped * clamped))]


def _faq_section(*rows: tuple[str, str, str]) -> dict[str, Any]:
    items = []
    for faq_id, question, answer in rows:
        items.append(
            {
                "qa_group_id": faq_id,
                "status": "active",
                "variants": [{"language": "en", "question": question, "answer": answer}],
            }
        )
    return {"items": items}


def _index_faq(tid: str, faq_id: str, question: str, doc_vec: list[float]) -> None:
    write_documents(
        None,
        [
            {
                "id": f"{tid}:{faq_id}:q",
                "tenant_id": tid,
                "space_id": ENTITY_DOCUMENT.space_id,
                "source_family": "faq",
                "source_id": faq_id,
                "chunk_id": "q0",
                "index_version": "v1",
                "source_revision": "v1",
                "content_hash": faq_id,
                "title": question,
                "search_text": question,
                "visible": True,
            }
        ],
        [doc_vec],
    )


def _turn(tid: str) -> CustomerTurn:
    return CustomerTurn(
        tenant_id=tid,
        conversation_id="c-faq",
        channel="instagram_dm",
        history=HistorySnapshot(),
        extra={"response_language": "en"},
    )


def test_pick_winner_threshold_and_ambiguous() -> None:
    high = StoreHit("a", "t", "faq", "qa1", "q", "q", 0.93)
    low = StoreHit("b", "t", "faq", "qa2", "q", "q", 0.89)
    other = StoreHit("c", "t", "faq", "qa3", "q", "q", 0.91)
    assert pick_faq_embed_winner([high, low]) == ("found", high)
    assert pick_faq_embed_winner([high, other])[0] == "ambiguous"
    assert pick_faq_embed_winner([low])[0] == "not_found"
    assert FAQ_COSINE_MIN == 0.90


def test_live_faq_path_has_no_soft_lexical_gate() -> None:
    src = (ROOT / "services/brain/faq_semantic.py").read_text(encoding="utf-8")
    assert "title_score" not in src
    assert "0.35" not in src
    assert "62.0" not in src
    live = (ROOT / "services/brain/faq_turn.py").read_text(encoding="utf-8")
    assert "faq_embed_result" in live


@pytest.mark.asyncio
async def test_embed_hit_sends_verbatim_without_llm(v2_env: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from services.brain.turn_pipeline import run_dm_after_gates

    tid = "t_faq_embed_hit"
    qvec, dvec = _pair(0.94)
    reset_memory_store()
    publish_pointer_content(tid, {"faq": _faq_section(("qa_laser", QUESTION, ANSWER))})
    _index_faq(tid, "qa_laser", QUESTION, dvec)
    llm_calls: list[str] = []
    agentic_calls: list[str] = []

    async def _embed(_text: str) -> list[float]:
        return qvec

    async def _llm(*_a: Any, **_k: Any) -> None:
        llm_calls.append("llm")
        raise AssertionError("FAQ hit must not call the answer LLM")

    async def _agentic(*_a: Any, **_k: Any) -> TurnResult:
        agentic_calls.append("agentic")
        return TurnResult(
            stop_reason="ok",
            envelope=FinalReplyEnvelope(
                decision="reply",
                messages=[OutboundMessage(destination="instagram_dm", text="terra")],
            ),
        )

    monkeypatch.setattr("services.brain.faq_embed.embed_faq_query", _embed)
    monkeypatch.setattr("services.brain.llm_core_service.create_chat_completion", _llm)
    monkeypatch.setattr("services.brain.agent.loop.run_agentic_dm_path", _agentic)
    monkeypatch.setattr("services.brain.turn_pipeline.try_confirm_pending", _no_confirm)
    out = await run_dm_after_gates(_turn(tid), message="How much is the laser session?", channel="instagram_dm")
    assert out.envelope.messages[0].text == ANSWER
    assert out.envelope.messages[0].protected is True
    assert (out.extra or {}).get("path") == "faq_embed_90"
    assert llm_calls == []
    assert agentic_calls == []


@pytest.mark.asyncio
async def test_score_089_falls_through_to_agentic(v2_env: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from services.brain.turn_pipeline import run_dm_after_gates

    tid = "t_faq_embed_miss"
    qvec, dvec = _pair(0.89)
    reset_memory_store()
    publish_pointer_content(tid, {"faq": _faq_section(("qa_laser", QUESTION, ANSWER))})
    _index_faq(tid, "qa_laser", QUESTION, dvec)

    async def _embed(_text: str) -> list[float]:
        return qvec

    async def _agentic(*_a: Any, **_k: Any) -> TurnResult:
        return TurnResult(
            stop_reason="ok",
            envelope=FinalReplyEnvelope(
                decision="reply",
                messages=[OutboundMessage(destination="instagram_dm", text="terra-path")],
            ),
            extra={"path": "agentic"},
        )

    monkeypatch.setattr("services.brain.faq_embed.embed_faq_query", _embed)
    monkeypatch.setattr("services.brain.agent.loop.run_agentic_dm_path", _agentic)
    monkeypatch.setattr("services.brain.turn_pipeline.try_confirm_pending", _no_confirm)
    out = await run_dm_after_gates(_turn(tid), message="How much is the laser session?", channel="instagram_dm")
    assert out.envelope.messages[0].text == "terra-path"
    assert (out.extra or {}).get("path") != "faq_embed_90"


@pytest.mark.asyncio
async def test_two_hits_at_090_do_not_auto_answer(v2_env: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from services.brain.turn_pipeline import run_dm_after_gates

    tid = "t_faq_embed_amb"
    qvec, dvec = _pair(0.92)
    reset_memory_store()
    publish_pointer_content(
        tid,
        {
            "faq": _faq_section(
                ("qa_a", "Laser price please?", ANSWER),
                ("qa_b", "Cost of laser?", "Thirty dollars."),
            )
        },
    )
    _index_faq(tid, "qa_a", "Laser price please?", dvec)
    _index_faq(tid, "qa_b", "Cost of laser?", dvec)

    async def _embed(_text: str) -> list[float]:
        return qvec

    async def _agentic(*_a: Any, **_k: Any) -> TurnResult:
        return TurnResult(
            stop_reason="ok",
            envelope=FinalReplyEnvelope(
                decision="reply",
                messages=[OutboundMessage(destination="instagram_dm", text="clarify-terra")],
            ),
            extra={"path": "agentic"},
        )

    monkeypatch.setattr("services.brain.faq_embed.embed_faq_query", _embed)
    monkeypatch.setattr("services.brain.agent.loop.run_agentic_dm_path", _agentic)
    monkeypatch.setattr("services.brain.turn_pipeline.try_confirm_pending", _no_confirm)
    out = await run_dm_after_gates(_turn(tid), message="laser cost?", channel="instagram_dm")
    assert out.envelope.messages[0].text == "clarify-terra"


@pytest.mark.asyncio
async def test_exact_match_still_wins_without_embed(v2_env: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from services.brain.turn_pipeline import run_dm_after_gates

    tid = "t_faq_exact_first"
    publish_pointer_content(tid, {"faq": _faq_section(("qa_laser", QUESTION, ANSWER))})
    embed_calls: list[str] = []

    async def _embed(_text: str) -> list[float] | None:
        embed_calls.append("embed")
        return None

    monkeypatch.setattr("services.brain.faq_embed.embed_faq_query", _embed)
    monkeypatch.setattr("services.brain.turn_pipeline.try_confirm_pending", _no_confirm)
    out = await run_dm_after_gates(_turn(tid), message=QUESTION, channel="instagram_dm")
    assert out.envelope.messages[0].text == ANSWER
    assert (out.extra or {}).get("path") == "faq_exact"
    assert embed_calls == []


async def _no_confirm(*_a: Any, **_k: Any) -> None:
    return None
