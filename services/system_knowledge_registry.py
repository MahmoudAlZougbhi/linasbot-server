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
            "Open Content Management from Control Center.",
            "Fill sections (basics, services, prices, FAQ, handoff…).",
            "Validate, then publish when ready (confirmation required).",
        ),
        tools=("read_cm", "validate_cm", "propose_cm_patch", "publish_cm"),
        blockers=("Publish needs confirmation and contentPublish permission.",),
        keywords=("cm", "content management", "setup", "draft", "configure", "ai know"),
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
        description="Create post drafts in Creative Studio.",
        route="create",
        entitlement=None,
        status="available",
        help_steps=("Open Create Post from Control Center or chat + sheet.",),
        tools=("read_scheduled_posts",),
        keywords=("create post", "creative", "caption", "generate"),
        tags=("creative",),
    ),
    Capability(
        feature="scheduled_posts",
        description="Upcoming scheduled posts for connected accounts.",
        route="scheduled",
        entitlement=None,
        status="available",
        help_steps=("Open Scheduled from Control Center.",),
        tools=("read_scheduled_posts",),
        keywords=("schedule", "scheduled", "upcoming posts"),
        tags=("creative",),
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
        description="Operator inbox for live customer conversations (ops).",
        route="livechat",
        entitlement=None,
        status="available",
        help_steps=("Open Live Chat from Control Center.",),
        tools=("get_recent_customer_interactions", "get_interaction_trace"),
        keywords=("live chat", "inbox", "operator", "bad reply", "diagnos"),
        tags=("ops", "diagnosis"),
    ),
    Capability(
        feature="smart_answers_faq",
        description="FAQ Smart Answers — semantic Q→A fast path with plan entitlements/quota.",
        route="cm",
        entitlement="faq_enabled",
        status="available",
        help_steps=(
            "Open Content Management → FAQ / Smart Answers.",
            "Quota is plan-based (e.g. 143 / 200); upgrade when at limit.",
            "Ask the copilot to save a Smart Answer (approval required).",
        ),
        tools=("read_faq_quota", "propose_smart_answer", "approve_smart_answer"),
        blockers=("No paid plan → FAQ disabled. Entry plans ~200; higher ~1000.",),
        keywords=("faq", "smart answer", "quota", "smart answers"),
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
        feature="comments",
        description="Comment automation — code present, not live-verified.",
        route="comments",
        entitlement="comment_automation",
        status="gated",
        help_steps=("Comments stay gated until Meta App Review + live_verified.",),
        tools=("read_integrations",),
        blockers=("Not live-verified; do not claim production comment automation.",),
        keywords=("comments", "comment reply"),
        tags=("integrations",),
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
        description="App settings, language, legal links, version.",
        route="settings",
        entitlement=None,
        status="available",
        help_steps=("Open Settings from Control Center.", "Set preferred language and display name."),
        tools=("read_profile", "update_profile"),
        keywords=("settings", "language", "profile", "address me"),
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
        "comments",
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
