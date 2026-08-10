"""Centralized OpenAI model-routing policy for Linas AI (single source of truth).

Binding rules:
- Owner surfaces → gpt-5.6-sol + reasoning mode standard + effort low|high
- Customer IG/FB DMs + comments → gpt-5.6-terra + standard + medium
- No Pro mode. No silent model/effort overrides from env.
"""

from __future__ import annotations

import hashlib
import os
import re
import time
from dataclasses import asdict, dataclass
from typing import Any, Literal

OwnerEffort = Literal["low", "high"]
CustomerEffort = Literal["medium"]
ReasoningMode = Literal["standard"]
ReasoningEffort = Literal["low", "medium", "high"]
ModelSurface = Literal[
    "owner_copilot",
    "owner_cm_ai",
    "owner_setup",
    "owner_chat",
    "owner_tool_continuation",
    "customer_ig_dm",
    "customer_fb_dm",
    "customer_ig_comment",
    "customer_fb_comment",
    "customer_social_retry",
    "customer_social_continuation",
]

MODEL_OWNER_SOL = "gpt-5.6-sol"
MODEL_CUSTOMER_TERRA = "gpt-5.6-terra"
REASONING_MODE_STANDARD: ReasoningMode = "standard"

# Env keys that must not silently diverge from this policy for reply/routing surfaces.
_OWNER_MODEL_ENV_KEYS = (
    "LINAS_OWNER_MODEL",
    "LINAS_OWNER_HELP_MODEL",
    "LINAS_OWNER_CM_MODEL",
    "LINAS_MODEL_OWNER_CHAT",
    "LINAS_MODEL_SETUP",
    "LINAS_MODEL_CREATIVE",
    "LINAS_CREATIVE_MODEL",
)
_CUSTOMER_MODEL_ENV_KEYS = (
    "LINAS_CUSTOMER_MODEL",
    "LINAS_CM_ANSWER_MODEL",
    "LINAS_MODEL_CUSTOMER_DM",
    "LINAS_CUSTOMER_HV_MODEL",
)

# Trusted mutation / write metadata (tools + intents). Prefer these over free-text keywords.
OWNER_MUTATION_TOOLS = frozenset(
    {
        "propose_cm_patch",
        "approve_cm_patch",
        "publish_cm",
        "propose_diagnosis_fix",
        "approve_diagnosis_fix",
        "propose_smart_answer",
        "approve_smart_answer",
        "update_profile",
        "extract_price_list",
        "setup_next_step",
    }
)
OWNER_MUTATION_INTENTS = frozenset(
    {
        "propose_cm_patch",
        "approve_cm_patch",
        "publish_cm",
        "propose_diagnosis_fix",
        "approve_diagnosis_fix",
        "propose_smart_answer",
        "approve_smart_answer",
        "update_profile",
        "extract_price_list",
        "setup_next_step",
        "create_creative_draft",
        "schedule_creative_draft",
    }
)
OWNER_READONLY_INTENTS = frozenset(
    {
        "help",
        "read_usage",
        "read_subscription",
        "read_integrations",
        "validate_cm",
        "read_cm",
        "read_dashboard_metrics",
        "read_scheduled_posts",
        "read_jobs_errors",
        "read_profile",
        "read_account_summary",
        "get_recent_customer_interactions",
        "get_interaction_trace",
        "read_faq_quota",
        "diagnose_meta_health",
    }
)

# Secondary signals only when trusted intent/tool metadata is absent.
# Uncertain write/design → Owner High (policy). Domain alone is not enough.
_STRONG_WRITE_VERB = re.compile(
    r"\b(create|add|update|rewrite|import|publish|enable|disable|remove|delete|configure|design)\b|"
    r"(انشر|احذف|أضف|اضف|فعّل|فعل|عطّل|عطل|استورد|صمم)",
    re.I,
)
_CHANGE_VERB = re.compile(
    r"\b(change|set|edit|modify|adjust|fix)\b|"
    r"(عدّل|عدل|غيّر|غير)",
    re.I,
)
_WRITE_DOMAIN = re.compile(
    r"\b(price|prices|branch|branches|faq|handoff|off\s*days?|ai\s*style|response\s*style|"
    r"ai\s*basics|dynamic\s*messages|care\s*instructions|restricted|services|languages|"
    r"ai\s*limits|landing\s*page|ui|ux|workflow|setting|settings|section)\b",
    re.I,
)
_DESIGN_MUTATION = re.compile(
    r"\b(app|web|landing)\b.{0,40}\b(design|ui|ux)\b|\b(design|ui|ux)\b.{0,40}\b(change|update)\b",
    re.I,
)


@dataclass(frozen=True)
class ModelPolicyDecision:
    surface: ModelSurface
    model: str
    reasoning_mode: ReasoningMode
    reasoning_effort: ReasoningEffort
    reason: str
    request_id: str = ""

    def to_safe_dict(self) -> dict[str, Any]:
        """Privacy-safe observability payload (no message content / PII)."""
        return {
            "surface": self.surface,
            "model": self.model,
            "reasoning_mode": self.reasoning_mode,
            "reasoning_effort": self.reasoning_effort,
            "reason": self.reason,
            "request_id": self.request_id,
        }


def _new_request_id(surface: str) -> str:
    return hashlib.sha256(f"{time.time_ns()}:{surface}".encode()).hexdigest()[:16]


def _normalize_confirm_intent(confirm_tool: str | None) -> str | None:
    if not confirm_tool:
        return None
    raw = confirm_tool.strip()
    if raw.startswith("approve_cm_patch"):
        return "approve_cm_patch"
    if raw.startswith("approve_diagnosis_fix"):
        return "approve_diagnosis_fix"
    if raw.startswith("approve_smart_answer"):
        return "approve_smart_answer"
    return raw


def classify_owner_effort(
    *,
    intent: str | None = None,
    confirm_tool: str | None = None,
    tool_names: list[str] | None = None,
    attachment_action: Literal["none", "analyze", "import"] | None = None,
    mutation_hint: bool | None = None,
    user_text: str | None = None,
    force_high: bool = False,
    force_low: bool = False,
    owner_mode: Literal["chat", "work"] | None = None,
) -> tuple[OwnerEffort, str]:
    """Resolve owner reasoning effort for one request (kept for all continuations).

    UI Chat|Work mode is authoritative when provided:
    - work → high (solo high)
    - chat → low (solo low / normal)
    ``force_high`` still wins (e.g. confirm_tool mutations).
    """
    if force_high:
        return "high", "force_high"
    if owner_mode == "work":
        return "high", "owner_mode_work"
    if owner_mode == "chat" or force_low:
        return "low", "owner_mode_chat" if owner_mode == "chat" else "force_low"
    confirm_intent = _normalize_confirm_intent(confirm_tool)
    if confirm_intent and confirm_intent in OWNER_MUTATION_INTENTS:
        return "high", f"confirm_tool={confirm_intent}"
    if intent and intent in OWNER_MUTATION_INTENTS:
        return "high", f"intent={intent}"
    tools = {str(t) for t in (tool_names or []) if t}
    mutating_tools = sorted(tools & OWNER_MUTATION_TOOLS)
    if mutating_tools:
        return "high", f"tools={','.join(mutating_tools)}"
    if mutation_hint is True:
        return "high", "mutation_hint"
    if attachment_action == "import":
        return "high", "attachment_import"
    if intent and intent in OWNER_READONLY_INTENTS:
        if attachment_action == "analyze":
            return "low", f"intent={intent}+attachment_analyze"
        return "low", f"intent={intent}"
    if attachment_action == "analyze" and not (user_text or "").strip():
        return "low", "attachment_analyze_only"
    text = (user_text or "").strip()
    if text:
        if _STRONG_WRITE_VERB.search(text):
            return "high", "strong_write_verb_or_ambiguous"
        if _CHANGE_VERB.search(text) and _WRITE_DOMAIN.search(text):
            return "high", "change_verb_with_domain"
        if _DESIGN_MUTATION.search(text):
            return "high", "design_or_ui_mutation"
    if attachment_action == "analyze":
        return "low", "attachment_analyze"
    return "low", "ordinary_readonly"


def resolve_owner_policy(
    *,
    surface: ModelSurface = "owner_copilot",
    intent: str | None = None,
    confirm_tool: str | None = None,
    tool_names: list[str] | None = None,
    attachment_action: Literal["none", "analyze", "import"] | None = None,
    mutation_hint: bool | None = None,
    user_text: str | None = None,
    force_high: bool = False,
    force_low: bool = False,
    owner_mode: Literal["chat", "work"] | None = None,
    request_id: str | None = None,
    prior: ModelPolicyDecision | None = None,
) -> ModelPolicyDecision:
    """Owner-facing policy. Continuations must pass ``prior`` to keep model+effort stable."""
    if prior is not None:
        return ModelPolicyDecision(
            surface="owner_tool_continuation",
            model=MODEL_OWNER_SOL,
            reasoning_mode=REASONING_MODE_STANDARD,
            reasoning_effort=prior.reasoning_effort,
            reason=f"continuation_of:{prior.reason}",
            request_id=prior.request_id or request_id or _new_request_id(surface),
        )
    effort, reason = classify_owner_effort(
        intent=intent,
        confirm_tool=confirm_tool,
        tool_names=tool_names,
        attachment_action=attachment_action,
        mutation_hint=mutation_hint,
        user_text=user_text,
        force_high=force_high,
        force_low=force_low,
        owner_mode=owner_mode,
    )
    return ModelPolicyDecision(
        surface=surface,
        model=MODEL_OWNER_SOL,
        reasoning_mode=REASONING_MODE_STANDARD,
        reasoning_effort=effort,
        reason=reason,
        request_id=request_id or _new_request_id(surface),
    )


def resolve_customer_social_policy(
    *,
    channel: str,
    surface: ModelSurface | None = None,
    continuation: bool = False,
    regeneration: bool = False,
    request_id: str | None = None,
) -> ModelPolicyDecision:
    """All Instagram/Facebook conversational LLM calls → Terra + medium."""
    ch = (channel or "").strip().lower()
    if surface is None:
        if regeneration or continuation:
            surface = "customer_social_retry" if regeneration else "customer_social_continuation"
        elif "comment" in ch:
            surface = "customer_ig_comment" if "instagram" in ch or ch in {"ig", "instagram"} else "customer_fb_comment"
        elif "facebook" in ch or ch in {"fb", "messenger", "page"}:
            surface = "customer_fb_dm"
        else:
            surface = "customer_ig_dm"
    reason = "customer_social_terra_medium"
    if regeneration:
        reason = "customer_social_regeneration"
    elif continuation:
        reason = "customer_social_continuation"
    return ModelPolicyDecision(
        surface=surface,
        model=MODEL_CUSTOMER_TERRA,
        reasoning_mode=REASONING_MODE_STANDARD,
        reasoning_effort="medium",
        reason=reason,
        request_id=request_id or _new_request_id(surface),
    )


def owner_model_id() -> str:
    return MODEL_OWNER_SOL


def customer_social_model_id() -> str:
    return MODEL_CUSTOMER_TERRA


def assert_customer_social_model(model: str) -> str:
    """Fail closed: never allow Sol/Luna/legacy on customer social reply paths."""
    m = (model or "").strip()
    if m != MODEL_CUSTOMER_TERRA:
        raise RuntimeError(f"customer_social_model_violation: expected {MODEL_CUSTOMER_TERRA}, got {m or '<empty>'}")
    return m


def emit_model_policy_trace(
    decision: ModelPolicyDecision,
    *,
    response_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Structured privacy-safe routing observation (never logs content/tokens/PII)."""
    row = decision.to_safe_dict()
    if response_id:
        row["response_id"] = response_id
    if extra:
        for key, value in extra.items():
            if key in {"message", "content", "text", "prompt", "tokens", "api_key", "authorization"}:
                continue
            row[key] = value
    print(
        "[model_policy] "
        f"surface={row.get('surface')} model={row.get('model')} "
        f"mode={row.get('reasoning_mode')} effort={row.get('reasoning_effort')} "
        f"reason={row.get('reason')} request_id={row.get('request_id')}"
        + (f" response_id={response_id}" if response_id else ""),
        flush=True,
    )
    return row


def validate_model_policy_config() -> dict[str, Any]:
    """Startup validation: env must not silently override the binding policy.

    Unset env is OK (policy hardcodes models). Set env must exactly match the
    policy model for that surface, otherwise fail clearly.
    """
    errors: list[str] = []
    seen: dict[str, str] = {}
    for key in _OWNER_MODEL_ENV_KEYS:
        raw = os.getenv(key)
        if raw is None or not str(raw).strip():
            continue
        value = str(raw).strip()
        seen[key] = value
        if value != MODEL_OWNER_SOL:
            errors.append(f"{key}={value!r} conflicts with owner policy model {MODEL_OWNER_SOL}")
    for key in _CUSTOMER_MODEL_ENV_KEYS:
        raw = os.getenv(key)
        if raw is None or not str(raw).strip():
            continue
        value = str(raw).strip()
        seen[key] = value
        if value != MODEL_CUSTOMER_TERRA:
            errors.append(f"{key}={value!r} conflicts with customer social policy model {MODEL_CUSTOMER_TERRA}")
    if errors:
        joined = "; ".join(errors)
        raise RuntimeError(
            "LINAS_MODEL_POLICY_INVALID: "
            f"{joined}. Unset these vars or set them to the policy models. "
            "Env cannot silently override Sol/Terra routing."
        )
    return {
        "owner_model": MODEL_OWNER_SOL,
        "customer_model": MODEL_CUSTOMER_TERRA,
        "reasoning_mode": REASONING_MODE_STANDARD,
        "env_checked": sorted(seen.keys()),
        "ok": True,
    }


def decision_as_dict(decision: ModelPolicyDecision) -> dict[str, Any]:
    return asdict(decision)
