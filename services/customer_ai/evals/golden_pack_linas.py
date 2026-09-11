"""Golden pack for Linas / hospitality-style Customer Brain offline checks."""

from __future__ import annotations

from typing import Any

from services.customer_ai.contracts.evidence import EvidenceBundle, EvidenceItem
from services.customer_ai.evals.fixtures import hospitality_corpus, service_appointment_corpus
from services.customer_ai.grounding.facts import evidence_supports_text, ungrounded_claims
from services.customer_ai.planner.heuristic import plan_message
from services.customer_ai.retrieve.cards import cards_from_sections
from services.customer_ai.retrieve.expand import expand_ranked
from services.customer_ai.retrieve.lexical import LexicalHit, search_cards


def _case(case_id: str, *, ok: bool, detail: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"id": case_id, "ok": ok, "detail": detail or {}}


def run_golden_pack_linas() -> dict[str, Any]:
    """Critical offline cases: FAQ, price, hours, ambiguity, fail-closed."""
    cases: list[dict[str, Any]] = []
    sections = {**hospitality_corpus(), **service_appointment_corpus()}
    cards = cards_from_sections(sections)

    # FAQ / information intent should plan read-only information or hours.
    plan_faq = plan_message("What are your opening hours?")
    cases.append(
        _case(
            "faq_hours_intent",
            ok=any(task.type in {"hours", "information"} for task in plan_faq.tasks),
            detail={"task_types": [t.type for t in plan_faq.tasks]},
        )
    )

    # Price query should retrieve service cards when present.
    price_hits = search_cards(cards, "laser hair removal price", families={"services"}, limit=3)
    price_ok = bool(price_hits) and price_hits[0].card.source_family == "services"
    cases.append(
        _case("price_lexical_hit", ok=price_ok, detail={"top": price_hits[0].card.item_id if price_hits else ""})
    )

    # Hours expand must carry clock times when corpus has them.
    hours_hits = search_cards(cards, "opening hours", families={"hours"}, limit=3) or search_cards(
        cards, "hours", limit=5
    )
    hours_bundle = expand_ranked(
        hours_hits or [LexicalHit(card=card, score=1.0) for card in cards[:1]],
        sections,
    )
    hours_text = " ".join(item.text for item in hours_bundle.items)
    cases.append(
        _case(
            "hours_evidence",
            ok=hours_bundle.outcome in {"found", "not_found"}
            and (":" in hours_text or hours_bundle.outcome != "found"),
            detail={"outcome": hours_bundle.outcome, "chars": len(hours_text)},
        )
    )

    # Ambiguity: multi-task plan should not collapse to a single family.
    multi = plan_message("What is the laser price and what are the branch hours?")
    families = {fam for task in multi.tasks for fam in task.source_families}
    cases.append(
        _case(
            "ambiguity_multi_family",
            ok=len(multi.tasks) >= 2 or len(families) >= 2,
            detail={"tasks": [t.type for t in multi.tasks], "families": sorted(families)},
        )
    )

    # Fail-closed grounding: invented price must not pass.
    bundle = EvidenceBundle(
        items=[
            EvidenceItem(
                evidence_id="services:laser",
                source_family="services",
                source_id="laser",
                text="Laser hair removal\n99.0 USD / session",
            )
        ]
    )
    invented = "Laser is 250 USD and we are open 03:00"
    cases.append(
        _case(
            "fail_closed_price",
            ok=not evidence_supports_text(invented, bundle) and bool(ungrounded_claims(invented, bundle)),
            detail={"claims": ungrounded_claims(invented, bundle)},
        )
    )
    cases.append(
        _case(
            "grounded_price_ok",
            ok=evidence_supports_text("Laser hair removal is 99.0 USD", bundle),
        )
    )

    # Empty evidence fail-closed.
    empty = EvidenceBundle(items=[])
    cases.append(_case("fail_closed_empty_evidence", ok=not evidence_supports_text("We open at 10:00", empty)))

    ok = all(bool(item.get("ok")) for item in cases)
    return {
        "ok": ok,
        "pack": "golden_pack_linas",
        "live_spend": False,
        "case_count": len(cases),
        "cases": cases,
    }
