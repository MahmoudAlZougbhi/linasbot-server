"""Deterministic (+ optional LLM) query interpretation for the FAQ-miss path (plan §12 step 10).

Runs ONLY after both exact and semantic FAQ miss. Deterministic extraction is always safe
(no network, no side effects) and MUST remain fully skippable — ``CM_INTERPRETER_LLM`` is
off by default, and callers may pass ``use_llm=False`` to force the deterministic-only path
regardless of environment (used by shadow eval and tests).
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any

from services.cm.schemas import BranchesSection, RestrictedPolicy, ServicesSection

#: Deterministic-only regexes. Safe to reuse (e.g. runtime_pipeline step 6) WITHOUT invoking
#: the async Query Interpreter, which per plan §12 must run only after FAQ miss (step 10).
BOOKING_INTENT_RE = re.compile(
    r"(?:book(?:ing)?|appointment|reserve|reservation|rendez[- ]?vous|\brdv\b|"
    r"حجز|احجز|أحجز|بدي\s*موعد|بدّي\s*موعد|(?<![A-Za-z])موعد)",
    re.IGNORECASE | re.UNICODE,
)
HUMAN_INTENT_RE = re.compile(
    r"(?:human\s*agent|speak\s*to\s*(?:someone|a\s*person|an?\s*agent)|representative|"
    r"موظف|حدا\s*يحكيني|بدي\s*احكي\s*مع\s*حدا|شخص\s*حقيقي)",
    re.IGNORECASE | re.UNICODE,
)


@dataclass
class InterpretedQuery:
    raw_text: str
    booking_requested: bool = False
    human_requested: bool = False
    restricted_topic_id: str | None = None
    service_id: str | None = None
    branch_id: str | None = None
    used_llm: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "raw_text": self.raw_text,
            "booking_requested": self.booking_requested,
            "human_requested": self.human_requested,
            "restricted_topic_id": self.restricted_topic_id,
            "service_id": self.service_id,
            "branch_id": self.branch_id,
            "used_llm": self.used_llm,
            "extra": self.extra,
        }


def interpreter_llm_enabled() -> bool:
    return os.getenv("CM_INTERPRETER_LLM", "false").strip().lower() in {"1", "true", "yes"}


def _text_mentions_any(text: str, markers: list[str]) -> bool:
    lowered = (text or "").lower()
    if not lowered:
        return False
    return any(marker.lower() in lowered for marker in markers if marker)


def _as_restricted(value: RestrictedPolicy | dict[str, Any] | None) -> RestrictedPolicy:
    if value is None:
        return RestrictedPolicy()
    if isinstance(value, RestrictedPolicy):
        return value
    return RestrictedPolicy.model_validate(value)


def _as_services(value: ServicesSection | dict[str, Any] | None) -> ServicesSection:
    if value is None:
        return ServicesSection()
    if isinstance(value, ServicesSection):
        return value
    return ServicesSection.model_validate(value)


def _as_branches(value: BranchesSection | dict[str, Any] | None) -> BranchesSection:
    if value is None:
        return BranchesSection()
    if isinstance(value, BranchesSection):
        return value
    return BranchesSection.model_validate(value)


def interpret_query_deterministic(
    message: str,
    *,
    services: ServicesSection | dict[str, Any] | None = None,
    branches: BranchesSection | dict[str, Any] | None = None,
    restricted: RestrictedPolicy | dict[str, Any] | None = None,
) -> InterpretedQuery:
    """Pure, deterministic extraction — no network calls, always safe to run."""
    text = message or ""
    result = InterpretedQuery(raw_text=text)
    result.booking_requested = bool(BOOKING_INTENT_RE.search(text))
    result.human_requested = bool(HUMAN_INTENT_RE.search(text))

    restricted_policy = _as_restricted(restricted)
    for topic in restricted_policy.topics:
        if not topic.active:
            continue
        markers = [topic.id, topic.labels.en, topic.labels.ar, topic.labels.fr, topic.labels.franco, *topic.keywords]
        if _text_mentions_any(text, [m for m in markers if m]):
            result.restricted_topic_id = topic.id
            break

    services_section = _as_services(services)
    for service in services_section.items:
        markers = [service.id, service.labels.en, service.labels.ar, service.labels.fr, *service.aliases]
        if _text_mentions_any(text, [m for m in markers if m]):
            result.service_id = service.id
            break

    branches_section = _as_branches(branches)
    for branch in branches_section.items:
        markers = [branch.id, branch.labels.en, branch.labels.ar, branch.labels.fr]
        if _text_mentions_any(text, [m for m in markers if m]):
            result.branch_id = branch.id
            break

    return result


async def interpret_query(
    message: str,
    *,
    services: ServicesSection | dict[str, Any] | None = None,
    branches: BranchesSection | dict[str, Any] | None = None,
    restricted: RestrictedPolicy | dict[str, Any] | None = None,
    use_llm: bool | None = None,
) -> InterpretedQuery:
    """Deterministic extraction, optionally enriched by a small, best-effort LLM call."""
    result = interpret_query_deterministic(message, services=services, branches=branches, restricted=restricted)
    should_use_llm = interpreter_llm_enabled() if use_llm is None else use_llm
    if not should_use_llm:
        return result
    try:
        await _enrich_with_llm(result)
    except Exception:
        pass  # Deterministic result remains valid; LLM enrichment is best-effort only.
    return result


async def _enrich_with_llm(result: InterpretedQuery) -> None:
    """Optional tiny LLM enrichment. Never required; caller must tolerate failure."""
    from services.llm_core_service import client as openai_client

    prompt = (
        "Extract intent as strict JSON only: "
        '{"booking_requested": bool, "human_requested": bool}. '
        "Do not invent business facts; only reflect what the message implies."
    )
    response = await openai_client.chat.completions.create(
        model="gpt-4o-mini",
        response_format={"type": "json_object"},
        messages=[{"role": "system", "content": prompt}, {"role": "user", "content": result.raw_text}],
    )
    content = (response.choices[0].message.content or "{}") if response.choices else "{}"
    parsed = json.loads(content)
    if isinstance(parsed.get("booking_requested"), bool):
        result.booking_requested = result.booking_requested or parsed["booking_requested"]
    if isinstance(parsed.get("human_requested"), bool):
        result.human_requested = result.human_requested or parsed["human_requested"]
    result.used_llm = True
