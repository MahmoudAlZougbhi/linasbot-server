"""Owner Copilot (Sol) CM schemas — portal-editable identity, not customer Terra."""

from __future__ import annotations

from pydantic import Field

from services.ai_setup.schemas_content import CmBaseModel


class SolBasics(CmBaseModel):
    """Published identity/style for Sol. Customer Terra never reads this section."""

    assistant_name: str = ""
    ai_role: str = ""
    tone: str = ""
    reply_style: str = ""
    identity_summary: str = ""
    advanced_instructions: str = ""
    do_list: list[str] = Field(default_factory=list)
    dont_list: list[str] = Field(default_factory=list)
    notes: str | None = None
