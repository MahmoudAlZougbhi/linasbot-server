"""Published CM capability gates for voice/image processing (AI Limits SoT)."""

from __future__ import annotations

from services.cm.constants import tenant_uses_cm_runtime
from services.cm.schemas import AiLimitsSection
from services.cm.version_store import PublishedVersionError, load_published_content


def _load_ai_limits(tenant_id: str) -> AiLimitsSection | None:
    tid = (tenant_id or "").strip() or "linas"
    if not tenant_uses_cm_runtime(tid):
        return None
    try:
        _pointer, sections = load_published_content(tid)
    except PublishedVersionError:
        return None
    return AiLimitsSection.model_validate(sections.get("ai_limits") or {})


def voice_processing_enabled(tenant_id: str) -> bool:
    """True when published AI Limits enable voice processing (default True)."""
    limits = _load_ai_limits(tenant_id)
    if limits is None:
        # Unpublished / no CM runtime: keep existing Linas ops behavior.
        return True
    return bool(limits.voice_processing_enabled)


def image_analysis_enabled(tenant_id: str) -> bool:
    """True when published AI Limits enable image analysis (default True)."""
    limits = _load_ai_limits(tenant_id)
    if limits is None:
        return True
    return bool(limits.image_analysis_enabled)
