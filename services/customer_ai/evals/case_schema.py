"""Eval case schema for the Customer Brain offline suite."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


CaseCategory = Literal[
    "retrieval",
    "grounding",
    "hallucination",
    "ambiguous",
    "insufficient_evidence",
    "contradiction",
    "stale",
    "prices",
    "hours",
    "phones",
    "urls",
    "branches",
    "services",
    "products",
    "stock",
    "booking",
    "faq",
    "handoff",
    "multi_intent",
    "noisy",
    "arabic",
    "lebanese_arabic",
    "arabizi",
    "english",
    "french",
    "mixed_language",
    "multi_turn",
    "injection",
    "irrelevant",
    "duplicate_chunks",
    "long_kb",
    "near_duplicate",
    "abstain",
]


LanguageTag = Literal["en", "ar", "lb", "arabizi", "fr", "mixed", ""]


@dataclass(frozen=True)
class EvalCase:
    case_id: str
    category: CaseCategory
    query: str
    language: LanguageTag = "en"
    relevant_ids: tuple[str, ...] = ()
    evidence_text: str = ""
    candidate_reply: str = ""
    expected: Literal[
        "retrieve",
        "grounded_ok",
        "ungrounded",
        "abstain",
        "clarify",
        "contradiction",
        "handoff",
        "reject_injection",
    ] = "retrieve"
    tags: tuple[str, ...] = ()
    conversation: tuple[dict[str, str], ...] = ()
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "category": self.category,
            "query": self.query,
            "language": self.language,
            "relevant_ids": list(self.relevant_ids),
            "evidence_text": self.evidence_text,
            "candidate_reply": self.candidate_reply,
            "expected": self.expected,
            "tags": list(self.tags),
            "conversation": list(self.conversation),
            "meta": dict(self.meta),
        }
