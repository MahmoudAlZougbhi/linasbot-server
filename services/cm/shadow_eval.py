"""Constrained shadow evaluation (plan §12.3 / Phase 5): Lab/golden/replay lists ONLY.

Hard constraint: this module MUST NEVER be imported from, or invoked on, the live webhook /
message-send path. It never calls a send function and never writes to production customer
history — it only reads FAQ/semantic-index data and returns an in-memory report.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from services.cm.query_interpreter import interpret_query
from services.cm.semantic_index import index_exists, search
from services.local_qa_service import local_qa_service


@dataclass
class ShadowQuestionResult:
    id: str
    question: str
    language: str
    faq_hit: bool
    faq_tier: str | None
    interpreter_ran: bool
    semantic_top1_source_id: str | None
    semantic_top1_score: float | None
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "question": self.question,
            "language": self.language,
            "faq_hit": self.faq_hit,
            "faq_tier": self.faq_tier,
            "interpreter_ran": self.interpreter_ran,
            "semantic_top1_source_id": self.semantic_top1_source_id,
            "semantic_top1_score": self.semantic_top1_score,
            "error": self.error,
        }


@dataclass
class ShadowEvalReport:
    tenant_id: str
    started_at: str
    finished_at: str
    total_questions: int
    faq_hit_count: int
    results: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "total_questions": self.total_questions,
            "faq_hit_count": self.faq_hit_count,
            "results": self.results,
        }


async def run_shadow_eval(
    *,
    tenant_id: str,
    questions: list[dict[str, Any]],
    index_id: str | None = None,
    top_k: int = 3,
) -> ShadowEvalReport:
    """Evaluate a fixed offline question list. No outbound sends, no live/prod history writes.

    ``questions``: list of ``{"id": str, "question": str, "language": str}``.
    """
    started = datetime.now(UTC).isoformat()
    results: list[dict[str, Any]] = []
    faq_hits = 0
    index_available = bool(index_id) and index_exists(tenant_id, index_id)  # type: ignore[arg-type]

    for item in questions:
        qid = str(item.get("id") or item.get("question") or "")
        question = str(item.get("question") or "")
        language = str(item.get("language") or "ar")
        try:
            match = await local_qa_service.find_match_with_tier(question, language)
            faq_hit = match is not None
            faq_tier = match.get("tier") if match else None
            interpreter_ran = False
            top1_id: str | None = None
            top1_score: float | None = None

            if not faq_hit:
                await interpret_query(question, use_llm=False)
                interpreter_ran = True
                if index_available:
                    hits = await search(
                        tenant_id=tenant_id, index_id=str(index_id), query=question, kind="faq", top_k=top_k
                    )
                    if hits:
                        top1_id = hits[0].get("source_id")
                        top1_score = hits[0].get("score")

            if faq_hit:
                faq_hits += 1

            results.append(
                ShadowQuestionResult(
                    id=qid,
                    question=question,
                    language=language,
                    faq_hit=faq_hit,
                    faq_tier=faq_tier,
                    interpreter_ran=interpreter_ran,
                    semantic_top1_source_id=top1_id,
                    semantic_top1_score=top1_score,
                ).as_dict()
            )
        except Exception as exc:  # noqa: BLE001 - one bad row must not abort the offline batch
            results.append(
                ShadowQuestionResult(
                    id=qid,
                    question=question,
                    language=language,
                    faq_hit=False,
                    faq_tier=None,
                    interpreter_ran=False,
                    semantic_top1_source_id=None,
                    semantic_top1_score=None,
                    error=str(exc),
                ).as_dict()
            )

    finished = datetime.now(UTC).isoformat()
    return ShadowEvalReport(
        tenant_id=tenant_id,
        started_at=started,
        finished_at=finished,
        total_questions=len(questions),
        faq_hit_count=faq_hits,
        results=results,
    )
