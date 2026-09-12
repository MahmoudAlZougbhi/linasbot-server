"""Deterministic answer critic. Live turns do not add a second LLM round-trip."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from services.customer_ai.agent.task_coverage import evaluate_task_coverage, missing_tasks
from services.customer_ai.contracts.evidence import EvidenceBundle
from services.customer_ai.contracts.plan import PlannerPlan
from services.customer_ai.grounding.claims import claims_fail_closed, verify_claims
from services.customer_ai.grounding.contradiction import detect_amount_contradictions
from services.customer_ai.grounding.facts import ungrounded_claims


class VerifierResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: str = "PASS"
    unsupported_claims: list[str] = Field(default_factory=list)
    missing_tasks: list[str] = Field(default_factory=list)
    repair_instruction: str = ""
    coverage: dict[str, str] = Field(default_factory=dict)
    conflicts: list[Any] = Field(default_factory=list)
    source: str = "deterministic"

    @property
    def status(self) -> str:
        return self.verdict

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump()


VerifyResult = VerifierResult


def _deterministic(
    *,
    text: str,
    plan: PlannerPlan,
    bundle: EvidenceBundle,
    structured_facts: Any,
    receipts: list[str] | None,
    message: str,
) -> VerifierResult:
    conflicts = detect_amount_contradictions("\n".join(item.text for item in bundle.items))
    if conflicts:
        return VerifierResult(
            verdict="FAIL",
            unsupported_claims=["contradiction_detected"],
            repair_instruction="Do not pick a price when evidence conflicts; ask which applies.",
            conflicts=list(conflicts),
        )
    reasons = ungrounded_claims(text, bundle, receipts)
    verdicts = verify_claims(text, bundle, receipts=receipts)
    coverage = evaluate_task_coverage(plan, bundle, structured_facts)
    missing = missing_tasks(plan, coverage)
    if missing:
        return VerifierResult(
            verdict="FAIL",
            unsupported_claims=[str(item) for item in reasons],
            missing_tasks=list(missing),
            repair_instruction=(
                "Do not invent missing facts. Ask a short clarifying question or say the "
                f"published answer is unavailable for: {', '.join(missing)}."
            ),
            coverage={k: str(v) for k, v in coverage.items()},
        )
    if reasons or claims_fail_closed(verdicts):
        unsupported = reasons or [v.reason or v.status for v in verdicts if v.status != "SUPPORTED"]
        return VerifierResult(
            verdict="FAIL",
            unsupported_claims=[str(item) for item in unsupported],
            repair_instruction=(
                "Remove unsupported claims. Only use EVIDENCE/RECEIPTS/STRUCTURED FACTS. "
                f"Customer asked: {(message or '')[:160]}"
            ),
            coverage={k: str(v) for k, v in coverage.items()},
        )
    return VerifierResult(verdict="PASS", coverage={k: str(v) for k, v in coverage.items()})


async def verify_answer(
    *,
    reply_text: str = "",
    draft: str = "",
    plan: PlannerPlan,
    bundle: EvidenceBundle,
    structured_facts: Any = None,
    receipts: list[str] | None = None,
    message: str = "",
) -> VerifierResult:
    """Structured PASS/FAIL from published evidence. No extra LLM critic on the live path."""
    text = (reply_text or draft or "").strip()
    det = _deterministic(
        text=text,
        plan=plan,
        bundle=bundle,
        structured_facts=structured_facts,
        receipts=receipts,
        message=message,
    )
    if det.verdict == "FAIL":
        return det
    # Deterministic PASS is the live authority. Optional LLM critic was adding a
    # full extra round-trip and could FAIL a grounded reply into empty outbound.
    return det
