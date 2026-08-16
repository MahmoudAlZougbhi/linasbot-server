"""Shared validation helpers for Customer Reply V2 DM and comment runtimes."""

from __future__ import annotations

from services.cm.answer_packet import build_answer_packet
from services.cm.response_validator import validate_response
from services.cm.schemas import AnswerChunk, AnswerFact
from services.cm.version_store import load_published_content
from services.customer_reply_v2.models import RetrievalResult


def facts_to_answer_facts(retrieval: RetrievalResult) -> tuple[list[AnswerFact], list[AnswerChunk]]:
    facts: list[AnswerFact] = []
    chunks: list[AnswerChunk] = []
    for ev in retrieval.evidence:
        if ev.section_id in {"prices", "services", "branches", "handoff", "off_days"}:
            facts.append(AnswerFact(kind=ev.section_id, value=ev.content[:500], source_id=ev.source_id))
        else:
            chunks.append(AnswerChunk(source_id=ev.source_id, text=ev.content, score=None))
    return facts, chunks


def validate_candidate(
    *,
    tenant_id: str,
    candidate: str,
    retrieval: RetrievalResult,
    detected_language: str,
    response_language: str,
) -> tuple[bool, list[str]]:
    pointer, sections = load_published_content(tenant_id)
    facts, chunks = facts_to_answer_facts(retrieval)
    packet = build_answer_packet(
        tenant_id=tenant_id,
        content_version_id=pointer.content_version_id,
        index_version_id=pointer.index_version_id,
        detected_language=detected_language,
        response_language=response_language,
        sections=sections,
        facts=facts,
        chunks=chunks,
    )
    result = validate_response(candidate, packet)
    return result.ok, list(result.failed_rules or [])


def safe_failure_reply(response_language: str, *, kind: str = "validation", public: bool = False) -> str:
    if kind == "model":
        messages = {
            "ar": "الخدمة الذكية غير متاحة حالياً. تواصل معنا مباشرة وسنساعدك.",
            "en": "Our AI reply service is temporarily unavailable. Please contact us directly.",
            "fr": "Le service de réponse IA est temporairement indisponible. Contactez-nous directement.",
            "franco": "El AI reply mesh available halla2. Contactuna mubasharan.",
        }
    elif kind == "insufficient":
        messages = {
            "ar": "ما قدرت أكد المعلومة من المحتوى المنشور حالياً. بقدر وجهك لفريقنا إذا حابب.",
            "en": "I couldn't confirm that from our published content. I can connect you with our team if you'd like.",
            "fr": "Je n'ai pas pu confirmer cela dans notre contenu publié. Je peux vous mettre en relation avec notre équipe.",
            "franco": "Ma ederet akked el maaloome men el content. Fini a3teek el team iza baddak.",
        }
    elif public:
        messages = {
            "ar": "خليني تأكدلك المعلومة صح — راسلنا بالخاص (DM) لنساعدك بدقة.",
            "en": "Let me make sure this is accurate — please message us in DM for a precise answer.",
            "fr": "Laissez-moi vérifier — écrivez-nous en message privé (DM) pour une réponse précise.",
            "franco": "Khallini akked el maaloome — rasilna bil DM la jawab sahih.",
        }
    else:
        messages = {
            "ar": "خليني تأكدلك المعلومة صح — راسلنا على واتساب لنساعدك بدقة.",
            "en": "Let me make sure this is accurate — please reach us on WhatsApp for a precise answer.",
            "fr": "Laissez-moi vérifier — contactez-nous sur WhatsApp pour une réponse précise.",
            "franco": "Khallini akked el maaloome — rasilna 3a WhatsApp la jawab sahih.",
        }
    return messages.get(response_language, messages["en"])
