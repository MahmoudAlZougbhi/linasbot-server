"""Frozen contracts and CM control-plane constants (plan §2.4–2.7)."""

from __future__ import annotations

import os
from typing import Final

CM_SCHEMA_VERSION: Final[int] = 1

SUPPORTED_LANGUAGES: Final[tuple[str, ...]] = ("ar", "en", "fr", "franco")

# Frozen response mapping: Franco/Arabizi questions → Arabic answers.
RESPONSE_LANGUAGE_MAP: Final[dict[str, str]] = {
    "ar": "ar",
    "en": "en",
    "fr": "fr",
    "franco": "ar",
}

DEFAULT_TENANT_ID: Final[str] = os.getenv("LINASBOT_TENANT_ID", "linas").strip() or "linas"

# Initial Restricted defaults (plan D8) — owner may change in an approved published version.
INITIAL_RESTRICTED_TOPIC_IDS: Final[tuple[str, ...]] = (
    "tattoo_removal",
    "co2_laser",
    "pigmentation_removal",
    "facial_skin_cleaning",
)

INITIAL_RESTRICTED_LABELS: Final[dict[str, dict[str, str]]] = {
    "tattoo_removal": {
        "en": "Tattoo removal",
        "ar": "إزالة الوشم",
        "fr": "Détatouage",
    },
    "co2_laser": {
        "en": "CO2 laser",
        "ar": "ليزر CO2",
        "fr": "Laser CO2",
    },
    "pigmentation_removal": {
        "en": "Pigmentation removal",
        "ar": "إزالة التصبغات",
        "fr": "Traitement de la pigmentation",
    },
    "facial_skin_cleaning": {
        "en": "Facial / skin-cleaning sessions",
        "ar": "جلسات تنظيف البشرة / فيشل",
        "fr": "Soins du visage / nettoyage de peau",
    },
}


# Env: CM_RUNTIME_MODE=legacy|published (default legacy until Phase 8 rehearsal/cutover).
def cm_runtime_mode() -> str:
    mode = os.getenv("CM_RUNTIME_MODE", "legacy").strip().lower()
    return mode if mode in {"legacy", "published"} else "legacy"


def cm_publish_enabled() -> bool:
    """Publish is disabled until Phase 8 machinery enables it (plan Phase 2)."""
    return os.getenv("CM_PUBLISH_ENABLED", "false").strip().lower() in {"1", "true", "yes"}


def cm_faq_canonical() -> bool:
    """When true (default), Content Managers → FAQ is the only FAQ writer.

    Legacy `/training` redirects to CM FAQ, and legacy Bot Training write APIs are disabled.
    Set CM_FAQ_CANONICAL=false only for emergency rollback of write gating.
    """
    return os.getenv("CM_FAQ_CANONICAL", "true").strip().lower() in {"1", "true", "yes"}


FAQ_EXACT_THRESHOLD: Final[float] = 0.90

PUBLISH_DISABLED_MESSAGE: Final[str] = (
    "Publishing is not enabled yet. This phase saves drafts only. "
    "No customer-facing AI behavior will change until a later approved phase."
)

ANSWER_VALIDATION_FAILED_MESSAGE_KEY: Final[str] = "answer_validation_failed"

CM_SECTIONS: Final[tuple[str, ...]] = (
    "ai_basics",
    "languages",
    "style",
    "dynamic_messages",
    "services",
    "branches",
    "prices",
    "care",
    "knowledge",
    "faq",
    "handoff",
    "restricted",
)
