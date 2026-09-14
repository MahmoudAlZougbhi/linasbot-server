"""Owner welcome chips + setup prompts (ChatGPT-like onboarding)."""

from __future__ import annotations

from typing import Any, Literal

OwnerMode = Literal["chat", "work"]

# Stage-aware chips shown under the seeded welcome message.
_CHIP_ORDER: tuple[str, ...] = (
    "learn_app",
    "setup_guided",
    "setup_bulk",
    "continue_cm",
    "connect_meta",
    "check_plan",
)

_CHIP_DEFS: dict[str, dict[str, Any]] = {
    "learn_app": {
        "modes": ("chat",),
        "stages": ("new", "cm_partial", "cm_ready_no_integration", "fully_configured"),
        "labels": {
            "en": "Want to learn more about the app?",
            "ar": "حابب تعرف أكثر عن التطبيق؟",
            "fr": "En savoir plus sur l’app ?",
        },
        "prompt": (
            "Give me a clear tour of what Linas AI can do for my business: "
            "Owner Copilot, AI Setup (the AI that replies to customers), "
            "Meta DMs/comments, subscription/usage. Keep it simple and actionable."
        ),
    },
    "setup_guided": {
        "modes": ("work",),
        "stages": ("new", "cm_partial"),
        "labels": {
            "en": "Set up my reply AI step by step",
            "ar": "خلّينا نجهّز ذكاء الرد خطوة بخطوة",
            "fr": "Configurer mon IA de réponses pas à pas",
        },
        "prompt": (
            "I want to set up the AI that replies to my customers (AI Setup) "
            "in guided mode — one section at a time. "
            "Call cm_fill_plan action=start, skip DONE/filled sections, "
            "then work ONLY plan.focus with inspect_cm_guide and propose_cm_patch. "
            "Ask me the next question now."
        ),
    },
    "setup_bulk": {
        "modes": ("work",),
        "stages": ("new", "cm_partial"),
        "labels": {
            "en": "Set up from a full business description",
            "ar": "جهّز من وصف كامل للبزنس",
            "fr": "Configurer depuis une description complète",
        },
        "prompt": (
            "I want bulk AI Setup. Ask me for a complete business description and how I want "
            "the AI to reply (I may paste text and/or attach a file). "
            "When I provide it, call ingest_business_dump to distribute into AI Setup sections, "
            "then propose the first section for approval and continue after each approve."
        ),
    },
    "continue_cm": {
        "modes": ("work",),
        "stages": ("cm_partial",),
        "labels": {
            "en": "Continue filling missing AI Setup sections",
            "ar": "كمّل تعبئة أقسام إعداد الذكاء الاصطناعي الناقصة",
            "fr": "Continuer les sections Configuration IA manquantes",
        },
        "prompt": (
            "Continue finishing AI Setup. Call cm_fill_plan action=start, "
            "skip DONE sections, walk remaining one at a time with propose_cm_patch."
        ),
    },
    "connect_meta": {
        "modes": ("work",),
        "stages": ("new", "cm_partial", "cm_ready_no_integration", "fully_configured"),
        "labels": {
            "en": "Connect Instagram / Facebook",
            "ar": "ربط إنستغرام / فيسبوك",
            "fr": "Connecter Instagram / Facebook",
        },
        "prompt": (
            "Help me connect Instagram/Facebook for customer DMs and comments. "
            "Use read_integrations / diagnose_meta_health. Do not disconnect or rotate tokens."
        ),
    },
    "check_plan": {
        "modes": ("chat",),
        "stages": ("new", "cm_partial", "cm_ready_no_integration", "fully_configured"),
        "labels": {
            "en": "Check my subscription / plan",
            "ar": "شو وضع الاشتراك / الخطة؟",
            "fr": "Vérifier mon abonnement",
        },
        "prompt": "Check my subscription and plan entitlements with read_subscription. Explain clearly what I have.",
    },
}


def welcome_chip_prompts() -> frozenset[str]:
    """English tool prompts used by welcome chips (stable across UI locales)."""
    return frozenset(str(spec["prompt"]).strip() for spec in _CHIP_DEFS.values())


def is_welcome_chip_prompt(text: str) -> bool:
    """True when the turn is a seeded welcome-chip / UI start prompt (not free typing)."""
    normalized = (text or "").strip()
    if not normalized:
        return False
    return normalized in welcome_chip_prompts()


def welcome_chips(*, setup_stage: str, language: str = "en") -> list[dict[str, Any]]:
    """Tappable welcome chips for a new (or empty) owner chat."""
    lang = language if language in {"en", "ar", "fr"} else "en"
    stage = setup_stage or "new"
    out: list[dict[str, Any]] = []
    for chip_id in _CHIP_ORDER:
        spec = _CHIP_DEFS[chip_id]
        if stage not in spec["stages"]:
            continue
        mode: OwnerMode = "work" if "work" in spec["modes"] else "chat"
        labels = spec["labels"]
        out.append(
            {
                "id": chip_id,
                "label": labels.get(lang) or labels["en"],
                "mode": mode,
                "prompt": spec["prompt"],
            }
        )
    return out
