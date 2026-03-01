# -*- coding: utf-8 -*-
"""
Interaction Flow Logger - Tracks User ↔ Bot ↔ AI message flow for dashboard transparency.
Enable via INTERACTION_FLOW_DEBUG=1 or config.INTERACTION_FLOW_DEBUG.
"""

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional
from collections import deque

# In-memory buffer for dashboard (last N entries)
_FLOW_BUFFER: deque = deque(maxlen=200)


def is_flow_logging_enabled() -> bool:
    """Check if flow logging is enabled."""
    val = os.getenv("INTERACTION_FLOW_DEBUG", "1").lower()
    if val in ("1", "true", "yes", "on"):
        return True
    try:
        import config
        return getattr(config, "INTERACTION_FLOW_DEBUG", True)
    except Exception:
        return True  # Default on for transparency


def _mask_user_id(user_id: Any) -> str:
    """Mask user ID for display (privacy)."""
    s = str(user_id or "")
    if len(s) <= 4:
        return s
    return f"...{s[-4:]}"


def log_interaction(
    user_id: str,
    user_message: str,
    bot_to_user: str,
    source: str,
    *,
    user_name: Optional[str] = None,
    user_phone: Optional[str] = None,
    ai_query_summary: Optional[str] = None,
    ai_raw_response: Optional[str] = None,
    model: Optional[str] = None,
    tokens: Optional[int] = None,
    prompt_tokens: Optional[int] = None,
    completion_tokens: Optional[int] = None,
    response_time_ms: Optional[float] = None,
    qa_match_score: Optional[float] = None,
    tool_calls: Optional[List[str]] = None,
    flow_steps: Optional[List[Dict]] = None,
) -> None:
    """
    Log one interaction in the User → Bot → AI → Bot → User flow.

    Args:
        user_id: WhatsApp/user identifier
        user_message: What the user sent
        bot_to_user: What the bot sent back to the user
        source: "user" | "qa_database" | "gpt" | "dynamic_retrieval" | "rate_limit" | "moderation"
        ai_query_summary: Brief summary of what was sent to GPT (e.g. last N msgs)
        ai_raw_response: Raw GPT response (before parsing/tool handling)
        model: AI model used (e.g. gpt-4o-mini)
        tokens: Token count if available
        response_time_ms: Response time in ms
        qa_match_score: If from Q&A, the match score
        tool_calls: List of tool names called (e.g. ["check_next_appointment"])
    """
    if not is_flow_logging_enabled():
        return

    phone = user_phone or user_id
    entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "user_id": user_id,
        "user_id_masked": _mask_user_id(user_id),
        "user_name": (user_name or "").strip() or None,
        "user_phone": phone,
        "user_phone_masked": _mask_user_id(phone) if phone else None,
        "user_message": (user_message or "")[:500],
        "bot_to_user": (bot_to_user or "")[:1000],
        "source": source,
        "ai_query_summary": (ai_query_summary or "")[:1500] if ai_query_summary else None,
        "ai_raw_response": (ai_raw_response or "")[:2000] if ai_raw_response else None,
        "model": model,
        "tokens": tokens,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "response_time_ms": response_time_ms,
        "qa_match_score": qa_match_score,
        "tool_calls": tool_calls,
        "flow_steps": flow_steps[:35] if flow_steps else None,
    }

    _FLOW_BUFFER.append(entry)


def get_recent_flows(limit: int = 50, search_phone: Optional[str] = None) -> List[Dict[str, Any]]:
    """Get recent flow entries for dashboard. Optionally filter by phone (partial match)."""
    entries = list(_FLOW_BUFFER)[-limit * 3:]  # Fetch more when filtering
    if search_phone and search_phone.strip():
        q = search_phone.strip().replace(" ", "").replace("+", "").replace("-", "")
        if q:
            entries = [e for e in entries if q in (e.get("user_phone") or "").replace(" ", "").replace("+", "").replace("-", "") or q in (e.get("user_id") or "").replace(" ", "").replace("+", "").replace("-", "")]
    return entries[-limit:]


def clear_flows() -> None:
    """Clear flow buffer."""
    _FLOW_BUFFER.clear()
