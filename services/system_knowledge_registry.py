"""Canonical Linas AI product capability registry (System Knowledge Layer).

Targeted retrieval only — never dump the full registry into every owner-chat prompt.
Routes here must match real mobile Control Center areas / screens.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

CapabilityStatus = Literal[
    "available",
    "partial",
    "gated",
    "coming_later",
    "unavailable",
]


@dataclass(frozen=True)
class Capability:
    feature: str
    description: str
    route: str  # mobile ControlArea id or deep link key
    entitlement: str | None
    status: CapabilityStatus
    help_steps: tuple[str, ...]
    tools: tuple[str, ...]
    blockers: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()
    tags: tuple[str, ...] = field(default_factory=tuple)

    def to_public(self) -> dict[str, Any]:
        return asdict(self)


# Routes must stay in sync with mobile/linas-ai/src/features/control/controlAreas.ts
CAPABILITIES: tuple[Capability, ...] = (
    Capability(
        feature="system_copilot",
        description="Main chat is the Linas AI System Copilot — brain of the whole app.",
        route="chat",
        entitlement=None,
        status="available",
        help_steps=(
            "Open the main chat after sign-in.",
            "Ask in plain language; use Control Center for screens.",
            "Approve high-impact changes before they apply.",
        ),
        tools=("help", "read_profile", "read_account_summary"),
        keywords=("help", "what can you do", "capabilities", "copilot", "linas"),
        tags=("core",),
    ),
    Capability(
        feature="content_management",
        description="Configure what your customer AI knows (draft → validate → publish).",
        route="cm",
        entitlement="contentManagers",
        status="available",
        help_steps=(
            "Ask the copilot what is filled vs missing, or open AI Setup.",
            "On review/check/problem asks, inspect_cm_guide runs a proactive quality_pass "
            "(critique, duplicates, unclear, improvements, suspicious) — not only the named topic.",
            "Use inspect_cm_guide / cm_fill_plan to walk remaining gaps one section at a time (skip DONE).",
            "Approve draft proposals, validate, then publish when ready (confirmation required).",
            "Languages: owners can enable/disable supported languages and set the default; "
            "the answer map is fixed (sabtin) — EN→EN, AR→AR, FR→FR, Franco→AR — cannot be changed.",
        ),
        tools=(
            "inspect_cm_guide",
            "cm_fill_plan",
            "read_cm",
            "validate_cm",
            "propose_cm_patch",
            "publish_cm",
        ),
        blockers=("Publish needs confirmation and contentPublish permission.",),
        keywords=(
            "cm",
            "content management",
            "ai setup",
            "setup",
            "draft",
            "configure",
            "ai know",
            "missing",
            "filled",
            "complete",
            "weak",
            "fill missing",
            "what is left",
            "section",
            "faq",
            "hours",
            "services",
            "prices",
            "handoff",
            "languages",
            "reply language",
            "customer language",
            "dm language",
            "comment language",
            "franco",
        ),
        tags=("cm", "setup"),
    ),
    Capability(
        feature="integrations_meta",
        description="Connect Meta (Instagram/Facebook). Truthful readiness — no fake live capabilities.",
        route="integrations",
        entitlement=None,
        status="partial",
        help_steps=(
            "Open Integrations from Control Center.",
            "Connect Meta when credentials and permissions allow.",
            "Comments/publish stay gated until live_verified.",
        ),
        tools=("read_integrations",),
        blockers=("comment_read/reply and content_publish require App Review + live_verified.",),
        keywords=("instagram", "facebook", "meta", "integrat", "connect"),
        tags=("integrations",),
    ),
    Capability(
        feature="usage_credits",
        description="Inspect included usage balance and credit wallet.",
        route="usage",
        entitlement=None,
        status="available",
        help_steps=("Open Usage & Credits from Control Center.", "Ask the copilot for a usage snapshot."),
        tools=("read_usage",),
        keywords=("usage", "credits", "wallet", "how much"),
        tags=("billing",),
    ),
    Capability(
        feature="billing_subscription",
        description="Plan entitlements and billing surface (store IAP may still be gated).",
        route="subscription",
        entitlement=None,
        status="partial",
        help_steps=("Open Billing from Control Center.", "Ask about your current plan."),
        tools=("read_subscription",),
        blockers=("Apple/Google IAP purchase_ready may be false until sandbox products exist.",),
        keywords=("subscription", "plan", "billing", "entitlement"),
        tags=("billing",),
    ),
    Capability(
        feature="creative_studio",
        description="Cancelled: social post/image/video creation is out of product scope (DM/comment automation only).",
        route="create",
        entitlement=None,
        status="unavailable",
        help_steps=(
            "Creative Studio is cancelled for the current product.",
            "Linas AI focuses on Instagram/Facebook DMs and comments.",
            "Use AI Setup, Integrations, and diagnosis instead.",
        ),
        tools=(),
        blockers=("Creative product cancelled in System Copilot V2.",),
        keywords=("create post", "creative", "caption", "generate", "بوست", "منشور", "compress", "reel", "story"),
        tags=("creative", "cancelled"),
    ),
    Capability(
        feature="scheduled_posts",
        description="Cancelled: post scheduling is out of product scope.",
        route="scheduled",
        entitlement=None,
        status="unavailable",
        help_steps=("Scheduling is not offered in the current product.",),
        tools=(),
        blockers=("Creative/scheduling cancelled in System Copilot V2.",),
        keywords=("schedule", "scheduled", "upcoming posts"),
        tags=("creative", "cancelled"),
    ),
    Capability(
        feature="dashboard_metrics",
        description="Tenant dashboard metrics and health summaries.",
        route="dashboard",
        entitlement=None,
        status="available",
        help_steps=("Open Dashboard from Control Center.",),
        tools=("read_dashboard_metrics",),
        keywords=("dashboard", "metrics", "stats", "health"),
        tags=("ops",),
    ),
    Capability(
        feature="live_chat",
        description="Read-only operator inbox for Instagram/Facebook customer conversations (no takeover/composer in V2).",
        route="livechat",
        entitlement=None,
        status="available",
        help_steps=(
            "Open Live Chat from Control Center to review customer threads.",
            "Live Chat is read-only — replies and takeover are not available in V2.",
            "Use System Copilot for diagnosis and CM fixes.",
        ),
        tools=("get_recent_customer_interactions", "get_interaction_trace", "diagnose_meta_health"),
        keywords=("live chat", "inbox", "operator", "bad reply", "diagnos"),
        tags=("ops", "diagnosis"),
    ),
    Capability(
        feature="smart_answers_faq",
        description=(
            "Smart Answers / FAQ — ready-made multilingual Q&A. When a customer asks the same "
            "question or same meaning, the bot answers from FAQ (automated reply) instead of a full "
            "AI generation, saving AI credits. Entries auto-translate to Arabic, English, French, "
            "and Franco (code: franco). Plan entitlements cap how many FAQ groups you can store."
        ),
        route="cm",
        entitlement="faq_enabled",
        status="available",
        help_steps=(
            "Open Smart Answers / FAQ (mobile Control Center) or AI Setup → FAQ (web).",
            "Check quota (e.g. 143 / 200); upgrade when at limit. Starter/Growth ~200; Pro/Max ~1000.",
            "Add in one language — the system creates the linked 4-language group (ar/en/fr/franco).",
            "Or ask Owner Copilot: “add this Q&A to FAQ” → proposal card → Approve → Live for customers.",
            "Matching customer questions hit FAQ first and skip LLM cost (see generations_avoided metrics).",
        ),
        tools=(
            "read_faq_quota",
            "propose_smart_answer",
            "approve_smart_answer",
            "list_cm_faq",
            "propose_cm_faq_upsert",
            "list_cm_faq",
            "propose_cm_delete",
        ),
        blockers=(
            "No paid plan → FAQ disabled. Entry plans ~200 groups; higher ~1000.",
            "Incomplete 4-language groups stay draft until complete.",
        ),
        keywords=("faq", "smart answer", "quota", "smart answers", "franco", "auto-translate", "save credits"),
        tags=("cm", "faq"),
    ),
    Capability(
        feature="self_diagnosis",
        description="Diagnose bad customer replies from TRACE evidence and apply approved fixes.",
        route="chat",
        entitlement=None,
        status="available",
        help_steps=(
            "Report a bad reply in main chat.",
            "Copilot finds the interaction TRACE and explains root cause.",
            "Approve the proposed correction — applied immediately (no Publish question).",
        ),
        tools=(
            "get_recent_customer_interactions",
            "get_interaction_trace",
            "propose_diagnosis_fix",
            "approve_diagnosis_fix",
        ),
        keywords=("diagnos", "wrong answer", "bad reply", "incorrect", "fix reply"),
        tags=("ops", "diagnosis"),
    ),
    Capability(
        feature="users_members",
        description="Workspace members and permissions.",
        route="users",
        entitlement=None,
        status="available",
        help_steps=("Open Users from Control Center.",),
        tools=("read_profile",),
        keywords=("users", "members", "permissions", "team"),
        tags=("account",),
    ),
    Capability(
        feature="settings",
        description=(
            "App settings and owner profile. App language (EN/AR/FR) is UI-only; "
            "it does not change Instagram/Facebook DM or comment reply language."
        ),
        route="settings",
        entitlement=None,
        status="available",
        help_steps=(
            "Open Settings from Control Center for app UI language and display name.",
            "Customer reply language for DMs/comments is AI Setup → Languages only "
            "(enable/disable + default). The Franco→Arabic (and EN/AR/FR identity) map is fixed.",
        ),
        tools=("read_profile", "update_profile"),
        keywords=("settings", "language", "profile", "address me", "app language", "ui language"),
        tags=("account",),
    ),
    Capability(
        feature="jobs_errors",
        description="Background job / queue error visibility when Redis workers are active.",
        route="dashboard",
        entitlement=None,
        status="partial",
        help_steps=("Ask about recent jobs or errors.", "Redis workers are opt-in via LINAS_REQUIRE_REDIS."),
        tools=("read_jobs_errors",),
        blockers=("Queue depth/errors unavailable when Redis/workers are not required/active.",),
        keywords=("jobs", "errors", "queue", "worker", "failed"),
        tags=("ops",),
    ),
)


_BY_FEATURE: dict[str, Capability] = {c.feature: c for c in CAPABILITIES}
_VALID_ROUTES: frozenset[str] = frozenset(
    {
        "chat",
        "cm",
        "create",
        "integrations",
        "usage",
        "subscription",
        "users",
        "scheduled",
        "settings",
        "dashboard",
        "livechat",
        "owner",
    }
)


def list_capabilities() -> list[Capability]:
    return list(CAPABILITIES)


def get_capability(feature: str) -> Capability | None:
    return _BY_FEATURE.get(feature)


def valid_mobile_routes() -> frozenset[str]:
    return _VALID_ROUTES


def registry_route_errors() -> list[str]:
    """Return human-readable errors when registry routes are not known mobile areas."""
    errors: list[str] = []
    for cap in CAPABILITIES:
        if cap.route not in _VALID_ROUTES:
            errors.append(f"{cap.feature}: unknown route {cap.route!r}")
    return errors
