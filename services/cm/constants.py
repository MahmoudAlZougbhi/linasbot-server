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
# Catalog is clinic-shaped historically; new tenants do not auto-activate these topics.
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


def cm_emergency_force_legacy() -> bool:
    """Retired. Classic GPT is gone; this flag no longer switches the customer engine."""
    return False


def cm_runtime_mode() -> str:
    """Diagnostic label. Customer AI is published-CM V2 or unpublished — never classic GPT."""
    return "published"


def cm_emergency_disable_publish() -> bool:
    """Ops kill switch: block publish/rollback for ALL tenants (default off)."""
    return os.getenv("CM_EMERGENCY_DISABLE_PUBLISH", "false").strip().lower() in {"1", "true", "yes"}


def cm_publish_enabled() -> bool:
    """Self-service publish is ON by default. Emergency disable blocks it."""
    if cm_emergency_disable_publish():
        return False
    raw = os.getenv("CM_PUBLISH_ENABLED")
    if raw is None or raw.strip() == "":
        return True
    return raw.strip().lower() in {"1", "true", "yes"}


def cm_faq_canonical() -> bool:
    """When true (default), AI Setup → FAQ is the only FAQ writer.

    Legacy `/training` redirects to CM FAQ, and legacy Bot Training write APIs are disabled.
    Set CM_FAQ_CANONICAL=false only for emergency rollback of write gating.
    """
    return os.getenv("CM_FAQ_CANONICAL", "true").strip().lower() in {"1", "true", "yes"}


FAQ_EXACT_THRESHOLD: Final[float] = 0.90

PUBLISH_DISABLED_MESSAGE: Final[str] = (
    "Publishing is temporarily disabled by an emergency ops switch. "
    "Drafts can still be edited. Contact support if this persists."
)

UNPUBLISHED_AI_MESSAGE: Final[dict[str, str]] = {
    "en": ("This AI is not published yet. Please finish AI Setup and publish before customers can get answers."),
    "ar": (
        "الذكاء الاصطناعي غير منشور بعد. أكمل إعداد الذكاء الاصطناعي وانشر المحتوى "
        "قبل أن يتمكن العملاء من الحصول على إجابات."
    ),
    "fr": (
        "Cette IA n'est pas encore publiée. Terminez la Configuration IA "
        "et publiez avant que les clients puissent obtenir des réponses."
    ),
    "franco": (
        "الذكاء الاصطناعي غير منشور بعد. أكمل إعداد الذكاء الاصطناعي وانشر المحتوى "
        "قبل أن يتمكن العملاء من الحصول على إجابات."
    ),
}

ANSWER_VALIDATION_FAILED_MESSAGE_KEY: Final[str] = "answer_validation_failed"

CM_SECTIONS: Final[tuple[str, ...]] = (
    "ai_basics",
    "languages",
    "style",
    "dynamic_messages",
    "services",
    "branches",
    "opening_hours",
    "prices",
    "care",
    "knowledge",
    "faq",
    "handoff",
    "restricted",
    "actions",
    "comments",
    "ai_limits",
    "off_days",
    "requests_appointments",
)


def tenant_has_published_cm(tenant_id: str | None) -> bool:
    """True when the tenant has a published CM pointer (does not verify checksums)."""
    from services.cm.version_store import read_published_pointer

    return read_published_pointer(tenant_id) is not None


def tenant_uses_cm_runtime(tenant_id: str | None) -> bool:
    """Per-tenant SoT: published CM drives Customer Reply V2 when present."""
    return tenant_has_published_cm(tenant_id)


def cm_disable_linas_legacy_bridge() -> bool:
    """Classic GPT bridge is gone. Kept as a durable env-file contract (always on)."""
    return True


def tenant_allows_legacy_bridge(tenant_id: str | None) -> bool:
    """Classic GPT / phases 3–12 are removed. Unpublished tenants get the unpublished message."""
    _ = tenant_id
    return False
