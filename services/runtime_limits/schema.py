"""Published CM payload for portal-tunable Brain / Sol runtime limits."""

from __future__ import annotations

from pydantic import Field

from services.ai_setup.schemas_content import CmBaseModel


class RuntimeLimitsSection(CmBaseModel):
    """Owner Portal → AI Setup → Runtime limits. Live published values drive runtime."""

    owner_history_messages: int = Field(default=100, ge=1, le=500)
    # 0 = unlimited (no per-message clip). Never default to 600.
    owner_message_max_chars: int = Field(default=0, ge=0, le=100000)
    customer_history_messages: int = Field(default=50, ge=1, le=500)
    customer_message_max_chars: int = Field(default=600, ge=0, le=10000)
    product_search_cap: int = Field(default=24, ge=1, le=200)
    catalog_evidence_cap: int = Field(default=18, ge=1, le=200)
    max_retrieval_rounds: int = Field(default=3, ge=1, le=10)
    max_agent_steps: int = Field(default=6, ge=1, le=20)
    max_tool_calls: int = Field(default=8, ge=1, le=20)
