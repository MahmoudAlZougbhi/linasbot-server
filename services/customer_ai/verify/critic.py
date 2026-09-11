"""Deterministic-first answer critic. Optional LLM only when OpenAI is configured."""

from __future__ import annotations

import os
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


async def _optional_llm(*, text: str, plan: PlannerPlan, bundle: EvidenceBundle) -> VerifierResult | None:
    if not (os.getenv("OPENAI_API_KEY") or "").strip():
        return None
    try:
        from services.customer_ai.providers.config import answer_model
        from services.llm_core_service import create_chat_completion

        evidence = "\n".join(f"- {item.title}: {item.text[:240]}" for item in bundle.items[:8])
        tasks = ", ".join(f"{t.id}:{t.type}" for t in plan.tasks)
        response = await create_chat_completion(
            model=answer_model(),
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Strict grounding critic. First line PASS or FAIL. Never invent.\n"
                        f"Tasks: {tasks}\nEvidence:\n{evidence}\nAnswer:\n{text}"
                    ),
                }
            ],
            max_tokens=200,
        )
        body = str(response.choices[0].message.content or "").strip()
        if not body:
            return None
        first = body.splitlines()[0].strip().upper()
        if first.startswith("PASS"):
            return VerifierResult(verdict="PASS", source="llm")
        claims = [line.strip("- ").strip() for line in body.splitlines()[1:] if line.strip()]
        return VerifierResult(
            verdict="FAIL",
            unsupported_claims=claims,
            repair_instruction="Revise using only published evidence; drop unsupported claims.",
            source="llm",
        )
    except Exception:
        return None


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
    """Structured PASS/FAIL. Deterministic first; on LLM failure use deterministic only."""
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
    llm = await _optional_llm(text=text, plan=plan, bundle=bundle)
    if llm is None:
        return det
    if llm.verdict == "FAIL":
        return llm
    return det
