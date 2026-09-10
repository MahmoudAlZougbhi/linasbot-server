"""Central Customer Brain model/provider IDs. Not Owner Copilot."""

from __future__ import annotations

import os
from typing import Any

from services.customer_ai.flags import voyage_configured
from services.customer_ai.providers.spaces import (
    ENTITY_MODEL,
    KNOWLEDGE_MODEL,
    MULTIMODAL_MODEL,
    RERANK_CANDIDATE,
    RERANK_MODEL,
    spaces_snapshot,
)
from services.model_policy import MODEL_CUSTOMER_TERRA
from services.providers.base import provider_config


def planner_model() -> str:
    return MODEL_CUSTOMER_TERRA


def answer_model() -> str:
    return MODEL_CUSTOMER_TERRA


def stt_model() -> str:
    return str(provider_config()["stt"].get("model") or "whisper-1")


def rerank_model() -> str:
    raw = (os.getenv("CUSTOMER_BRAIN_RERANK_MODEL") or "").strip()
    if raw == RERANK_CANDIDATE:
        return RERANK_CANDIDATE
    return RERANK_MODEL


def provider_status() -> dict[str, Any]:
    return {
        "openai_planner": planner_model(),
        "openai_answer": answer_model(),
        "openai_stt": stt_model(),
        "voyage_configured": voyage_configured(),
        "voyage_knowledge": KNOWLEDGE_MODEL,
        "voyage_entity": ENTITY_MODEL,
        "voyage_multimodal": MULTIMODAL_MODEL,
        "voyage_rerank": rerank_model(),
        "spaces": spaces_snapshot(),
    }
