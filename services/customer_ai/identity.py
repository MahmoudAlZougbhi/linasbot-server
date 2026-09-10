"""Load compact published AI Basic + Style. No prices or hours."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from services.cm.schemas import AiBasics, StylePolicy
from services.cm.version_store import PublishedVersionError, load_published_content


class IdentityBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assistant_name: str = ""
    business_name: str = ""
    ai_role: str = ""
    business_purpose: str = ""
    identity_summary: str = ""
    advanced_instructions: str = ""
    tone: str = ""
    formality: str = ""
    response_length: str = ""
    emoji_level: str = ""
    one_question_at_a_time: bool = True
    preferred_terms: list[str] = Field(default_factory=list)
    do_list: list[str] = Field(default_factory=list)
    dont_list: list[str] = Field(default_factory=list)
    style_body: str = ""


def _section(sections: dict[str, Any], *names: str) -> dict[str, Any]:
    for name in names:
        raw = sections.get(name)
        if isinstance(raw, dict):
            return raw
    return {}


def load_identity_bundle(tenant_id: str) -> IdentityBundle | None:
    tid = (tenant_id or "").strip()
    if not tid:
        return None
    try:
        _pointer, sections = load_published_content(tid)
    except PublishedVersionError:
        return None
    basics = AiBasics.model_validate(_section(sections, "ai_basics", "ai_basic", "basic"))
    style = StylePolicy.model_validate(_section(sections, "style", "style_policy"))
    return IdentityBundle(
        assistant_name=basics.assistant_name,
        business_name=basics.clinic_name,
        ai_role=basics.ai_role,
        business_purpose=basics.business_purpose,
        identity_summary=basics.identity_summary,
        advanced_instructions=basics.advanced_instructions,
        tone=style.tone,
        formality=style.formality,
        response_length=style.response_length,
        emoji_level=style.emoji_level,
        one_question_at_a_time=style.one_question_at_a_time,
        preferred_terms=list(style.preferred_terms),
        do_list=list(style.do_list),
        dont_list=list(style.dont_list),
        style_body=style.style_body,
    )
