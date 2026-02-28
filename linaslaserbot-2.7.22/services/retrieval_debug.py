# -*- coding: utf-8 -*-
"""
Retrieval Debug Logging - Structured JSON logging for smart retrieval.
Enable/disable via SMART_RETRIEVAL_DEBUG env or config.
"""

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional
from collections import deque

# In-memory buffer for admin debug panel (last N entries)
_DEBUG_BUFFER: deque = deque(maxlen=100)

# Enable/disable via env or explicit set
def is_debug_enabled() -> bool:
    val = os.getenv("SMART_RETRIEVAL_DEBUG", "").lower()
    if val in ("1", "true", "yes", "on"):
        return True
    try:
        import config
        return getattr(config, "SMART_RETRIEVAL_DEBUG", False)
    except Exception:
        return False


def _estimate_tokens(text: str) -> int:
    """Rough token estimate (~4 chars per token for mixed content)."""
    if not text:
        return 0
    return max(1, len(text) // 4)


def log_retrieval(
    user_message: str,
    detected_intent: str,
    detected_gender: Optional[str],
    selected_knowledge: List[Dict[str, Any]],
    selected_price: List[Dict[str, Any]],
    selected_style: List[Dict[str, Any]],
    faq_matched: bool,
    faq_match_score: Optional[float],
    prompt_token_estimate: Optional[int] = None,
    source: str = "faq" if faq_matched else "ai",
) -> None:
    """Log structured retrieval debug info."""
    if not is_debug_enabled():
        return

    entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "user_message": user_message[:500],
        "detected_intent": detected_intent,
        "detected_gender": detected_gender or "unknown",
        "selected_knowledge_files": [{"id": f.get("id"), "title": f.get("title")} for f in selected_knowledge],
        "selected_price_files": [{"id": f.get("id"), "title": f.get("title")} for f in selected_price],
        "selected_style_files": [{"id": f.get("id"), "title": f.get("title")} for f in selected_style],
        "faq_matched": faq_matched,
        "faq_match_score": faq_match_score,
        "source": source,
        "final_prompt_token_estimate": prompt_token_estimate,
    }

    _DEBUG_BUFFER.append(entry)

    try:
        line = json.dumps(entry, ensure_ascii=False) + "\n"
        print(f"[RETRIEVAL_DEBUG] {line}")
    except Exception as e:
        print(f"[RETRIEVAL_DEBUG] log error: {e}")


def get_recent_logs(limit: int = 50) -> List[Dict]:
    """Get recent retrieval logs for admin debug panel."""
    return list(_DEBUG_BUFFER)[-limit:]


def clear_logs() -> None:
    """Clear debug buffer."""
    _DEBUG_BUFFER.clear()
