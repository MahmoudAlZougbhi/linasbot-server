"""
Interaction Flow Logger - Tracks User ↔ Bot ↔ AI message flow for dashboard transparency.
Enable via INTERACTION_FLOW_DEBUG=1 or config.INTERACTION_FLOW_DEBUG.
Persists to LINASBOT_DATA_ROOT/logs/activity_flow.jsonl so data survives deploy/rebuild.
"""

from __future__ import annotations

import json
import os
import re
from collections import deque
from datetime import datetime
from typing import Any

from storage.persistent_storage import ACTIVITY_FLOW_FILE, ensure_dirs

FLOW_LOG_FILE = str(ACTIVITY_FLOW_FILE)
_BUFFER_MAXLEN = 500

# In-memory buffer for dashboard (last N entries) - loaded from file on startup
_FLOW_BUFFER: deque = deque(maxlen=_BUFFER_MAXLEN)
_INITIALIZED = False

_SECRET_RE = re.compile(r"(?i)\b(api[_-]?key|access[_-]?token|bearer|authorization|secret|password)\b\s*[:=]\s*\S+")


def _ensure_data_dir() -> None:
    """Ensure persistent logs directory exists."""
    ensure_dirs()


def _tail_lines(path: str, max_lines: int, max_bytes: int = 1024 * 1024) -> list[str]:
    """Read last max_lines from file without loading entire file (tail). max_bytes caps read size (default 1MB)."""
    if not os.path.isfile(path):
        return []
    size = os.path.getsize(path)
    if size == 0:
        return []
    try:
        with open(path, "rb") as f:
            to_read = min(size, max_bytes)
            f.seek(max(0, size - to_read))
            chunk = f.read()
        # Decode; if we seeked mid-UTF8, drop the first (possibly partial) line
        try:
            text = chunk.decode("utf-8")
        except UnicodeDecodeError:
            text = chunk.decode("utf-8", errors="replace")
        if size > max_bytes:
            first_nl = text.find("\n")
            if first_nl != -1:
                text = text[first_nl + 1 :]
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        return lines[-max_lines:] if len(lines) > max_lines else lines
    except OSError:
        return []


def _load_from_file() -> None:
    """Load last N entries from disk into buffer (called on first use). Uses tail to avoid reading whole file."""
    global _INITIALIZED
    if _INITIALIZED:
        return
    _INITIALIZED = True
    if not os.path.isfile(FLOW_LOG_FILE):
        return
    try:
        # Read only last N lines from file (tail); 1MB cap for fast first load
        lines = _tail_lines(FLOW_LOG_FILE, _BUFFER_MAXLEN * 2, max_bytes=1024 * 1024)
        for line in lines:
            try:
                entry = json.loads(line)
                _FLOW_BUFFER.append(entry)
            except json.JSONDecodeError:
                continue
    except OSError as e:
        print(f"⚠️ Could not load activity flow from {FLOW_LOG_FILE}: {e}")


def _append_to_file(entry: dict[str, Any]) -> None:
    """Append one entry to the persistent log file."""
    _ensure_data_dir()
    try:
        with open(FLOW_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as e:
        print(f"⚠️ Could not append to activity flow file: {e}")


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


def _redact_secrets(text: str | None, max_len: int) -> str | None:
    if not text:
        return None
    cleaned = _SECRET_RE.sub(r"\1=[REDACTED]", str(text))
    return cleaned[:max_len]


def resolve_interaction_channel(user_data: dict[str, Any] | None) -> str:
    """Normalize channel label for Interaction Logs (IG/FB/WA/Testing Lab)."""
    ud = user_data or {}
    if ud.get("_dashboard_test_simulation"):
        return "testing_lab"
    raw = str(ud.get("channel") or "").strip().lower()
    if raw in ("instagram", "ig"):
        return "instagram"
    if raw in ("facebook", "messenger", "fb"):
        return "facebook"
    if raw in ("whatsapp", "wa", "360dialog", "dialog360"):
        return "whatsapp"
    if raw in ("testing_lab", "dashboard", "test"):
        return "testing_lab"
    # Phone-based WhatsApp sessions typically omit channel.
    if ud.get("phone_number") or str(ud.get("provider") or "").lower() in ("whatsapp", "360dialog"):
        return "whatsapp"
    return raw or "unknown"


def safe_cm_diagnostics(metadata: dict[str, Any] | None) -> dict[str, Any] | None:
    """Keep only safe CM diagnostic fields (IDs/titles — no prompts/secrets)."""
    if not isinstance(metadata, dict) or not metadata:
        return None
    sources_raw = metadata.get("retrieved_sources")
    sources: list[dict[str, str]] = []
    if isinstance(sources_raw, list):
        for item in sources_raw[:30]:
            if isinstance(item, dict):
                sid = str(item.get("source_id") or item.get("id") or "")[:120]
                title = str(item.get("title") or item.get("text") or "")[:160]
                if sid or title:
                    sources.append({"source_id": sid, "title": title})
            elif item is not None:
                sources.append({"source_id": str(item)[:120], "title": ""})
    source_ids = metadata.get("source_ids")
    out: dict[str, Any] = {
        "reason": (str(metadata.get("reason") or "")[:120] or None),
        "content_version_id": (str(metadata.get("content_version_id") or "")[:120] or None),
        "index_version_id": (str(metadata.get("index_version_id") or "")[:120] or None),
        "validated": metadata.get("validated") if isinstance(metadata.get("validated"), bool) else None,
        "regenerated": metadata.get("regenerated") if isinstance(metadata.get("regenerated"), bool) else None,
        "source_ids": [str(x)[:120] for x in (source_ids or [])[:40]] if isinstance(source_ids, list) else [],
        "retrieved_sources": sources,
        "failed_rules": [str(x)[:80] for x in (metadata.get("failed_rules") or [])[:20]]
        if isinstance(metadata.get("failed_rules"), list)
        else [],
    }
    # Drop empty-only payloads
    if not any(v not in (None, [], "") for k, v in out.items() if k != "failed_rules"):
        return None
    return out


def _derive_cost_status(
    *,
    source: str,
    cost_usd: float | None,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    tokens: int | None,
    cost_status: str | None,
    ai_called: bool | None,
) -> str:
    if cost_status in ("estimated", "unavailable", "none", "actual"):
        return cost_status
    src = (source or "").lower()
    ai_sources = {
        "gpt",
        "dynamic_retrieval",
        "cm_runtime",
        "packet_ready",
        "answer_validation_failed",
    }
    called = ai_called if ai_called is not None else (src in ai_sources or src.startswith("cm_") or "gpt" in src)
    if not called:
        return "none"
    if cost_usd is not None:
        return "estimated"
    if prompt_tokens is not None or completion_tokens is not None or tokens is not None:
        return "unavailable"
    return "unavailable"


def log_interaction(
    user_id: str,
    user_message: str,
    bot_to_user: str,
    source: str,
    *,
    user_name: str | None = None,
    user_phone: str | None = None,
    user_gender: str | None = None,
    customer_exists: bool | None = None,
    customer_file_status: str | None = None,
    ai_query_summary: str | None = None,
    bot_sent_to_ai_full: str | None = None,
    customer_context_sent: str | None = None,
    ai_raw_response: str | None = None,
    model: str | None = None,
    tokens: int | None = None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    cost_usd: float | None = None,
    input_cost_usd: float | None = None,
    output_cost_usd: float | None = None,
    response_time_ms: float | None = None,
    qa_match_score: float | None = None,
    tool_calls: list[str] | None = None,
    flow_steps: list[dict] | None = None,
    flow_error: str | None = None,
    token_source: str | None = None,
    message_type: str | None = None,
    channel: str | None = None,
    direction: str | None = None,
    conversation_id: str | None = None,
    message_id: str | None = None,
    handler_path: str | None = None,
    outcome: str | None = None,
    pipeline_decisions: list[dict[str, Any]] | None = None,
    cm_diagnostics: dict[str, Any] | None = None,
    faq_match: dict[str, Any] | None = None,
    cost_status: str | None = None,
    cost_basis: str | None = None,
    ai_called: bool | None = None,
    user_data: dict[str, Any] | None = None,
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
        model: AI model used (e.g. gpt-5-mini)
        tokens: Token count if available
        response_time_ms: Response time in ms
        qa_match_score: If from Q&A, the match score
        tool_calls: List of tool names called (e.g. ["check_next_appointment"])
    """
    if not is_flow_logging_enabled():
        return

    _load_from_file()

    phone = user_phone or user_id
    store_full_prompts = (os.getenv("FLOW_LOG_FULL_PROMPTS") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    resolved_channel = channel or resolve_interaction_channel(user_data)
    resolved_tenant_id: str | None = None
    if isinstance(user_data, dict):
        raw_tid = user_data.get("tenant_id") or user_data.get("tenantId")
        if raw_tid:
            resolved_tenant_id = str(raw_tid).strip().lower() or None
    resolved_cost_status = _derive_cost_status(
        source=source,
        cost_usd=cost_usd,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        tokens=tokens,
        cost_status=cost_status,
        ai_called=ai_called,
    )
    safe_diag = safe_cm_diagnostics(cm_diagnostics) if cm_diagnostics else None
    safe_faq: dict[str, Any] | None = None
    if isinstance(faq_match, dict) and faq_match:
        safe_faq = {
            "faq_id": faq_match.get("faq_id"),
            "tier": (str(faq_match.get("tier") or "")[:40] or None),
            "similarity": faq_match.get("similarity")
            if isinstance(faq_match.get("similarity"), (int, float))
            else None,
            "stored_language": (str(faq_match.get("stored_language") or "")[:16] or None),
        }

    # Default: mask phones and truncate prompts — do not persist full customer prompts.
    entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "user_id": _mask_user_id(user_id),
        "user_id_masked": _mask_user_id(user_id),
        "user_name": (user_name or "").strip() or None,
        "user_phone": None,
        "user_phone_masked": _mask_user_id(phone) if phone else None,
        "user_gender": (user_gender or "").strip().lower() or "unknown",
        "customer_exists": customer_exists if isinstance(customer_exists, bool) else None,
        "customer_file_status": (customer_file_status or "").strip().lower() or None,
        "user_message": _redact_secrets(user_message, 500),
        "bot_to_user": _redact_secrets(bot_to_user, 1000),
        "source": source,
        "channel": resolved_channel,
        "tenant_id": resolved_tenant_id,
        "direction": (direction or "inbound").strip().lower()[:20],
        "conversation_id": (str(conversation_id)[:120] if conversation_id else None),
        "message_id": (str(message_id)[:120] if message_id else None),
        "handler_path": (str(handler_path)[:200] if handler_path else None),
        "outcome": (str(outcome or source)[:120] if (outcome or source) else None),
        "pipeline_decisions": (pipeline_decisions or [])[:40] or None,
        "cm_diagnostics": safe_diag,
        "faq_match": safe_faq,
        "ai_query_summary": (
            (
                _redact_secrets(ai_query_summary, 120000)
                if store_full_prompts
                else _redact_secrets(ai_query_summary, 500)
            )
            if ai_query_summary
            else None
        ),
        "bot_sent_to_ai_full": (
            (_redact_secrets(bot_sent_to_ai_full, 250000) if store_full_prompts else None)
            if bot_sent_to_ai_full
            else None
        ),
        "customer_context_sent": (
            (_redact_secrets(customer_context_sent, 50000) if store_full_prompts else None)
            if customer_context_sent
            else None
        ),
        "ai_raw_response": _redact_secrets(ai_raw_response, 500) if ai_raw_response else None,
        "model": model,
        "tokens": tokens,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "cost_usd": round(cost_usd, 6) if cost_usd is not None else None,
        "input_cost_usd": round(input_cost_usd, 6) if input_cost_usd is not None else None,
        "output_cost_usd": round(output_cost_usd, 6) if output_cost_usd is not None else None,
        "cost_status": resolved_cost_status,
        "cost_basis": (cost_basis or None)
        if resolved_cost_status == "estimated"
        else (cost_basis if cost_basis else None),
        "response_time_ms": response_time_ms,
        "qa_match_score": qa_match_score,
        "tool_calls": tool_calls,
        "flow_steps": flow_steps[:50] if flow_steps else None,
        "flow_error": _redact_secrets(flow_error, 2000) if flow_error else None,
        "token_source": (token_source or "")[:50] if token_source else None,
        "message_type": (message_type or "text").lower() if message_type else "text",
    }
    if entry["cost_status"] == "estimated" and not entry.get("cost_basis"):
        from services.model_pricing import COST_BASIS_TOKEN_RATES

        entry["cost_basis"] = COST_BASIS_TOKEN_RATES

    # Meter prepaid wallets using the same token fields as Interaction Logs.
    try:
        use_in = max(0, int(prompt_tokens or 0)) if isinstance(prompt_tokens, int) else 0
        use_out = max(0, int(completion_tokens or 0)) if isinstance(completion_tokens, int) else 0
        total_tokens = 0
        if isinstance(tokens, int):
            total_tokens = max(0, tokens)
        else:
            total_tokens = use_in + use_out
        if use_in > 0 or use_out > 0 or total_tokens > 0:
            from services.token_metering import debit_ai_usage, resolve_tenant_id

            tid = resolve_tenant_id(user_data if isinstance(user_data, dict) else None)
            debit_ai_usage(
                tenant_id=tid,
                prompt_tokens=use_in if use_in or use_out else None,
                completion_tokens=use_out if use_in or use_out else None,
                tokens=total_tokens if not (use_in or use_out) else None,
                cost_usd=float(cost_usd) if isinstance(cost_usd, (int, float)) else None,
                input_cost_usd=float(input_cost_usd) if isinstance(input_cost_usd, (int, float)) else None,
                output_cost_usd=float(output_cost_usd) if isinstance(output_cost_usd, (int, float)) else None,
                model=model,
                reference=str(message_id) if message_id else None,
            )
    except Exception as exc:
        # Never break interaction logging because of wallet accounting.
        print(f"[interaction_flow] token debit skipped: {type(exc).__name__}", flush=True)

    _FLOW_BUFFER.append(entry)
    _append_to_file(entry)

    # Persist safe customer-response TRACE for owner self-diagnosis (no chain-of-thought).
    if resolved_tenant_id:
        try:
            from services.customer_response_trace import persist_from_interaction_entry

            persist_from_interaction_entry(entry)
        except Exception as exc:
            print(f"[interaction_flow] TRACE persist skipped: {type(exc).__name__}", flush=True)


def get_recent_flows(limit: int = 50, search_phone: str | None = None) -> list[dict[str, Any]]:
    """Get recent flow entries for dashboard. Optionally filter by phone (partial match)."""
    _load_from_file()
    entries = list(_FLOW_BUFFER)[-limit * 3 :]  # Fetch more when filtering
    if search_phone and search_phone.strip():
        q = search_phone.strip().replace(" ", "").replace("+", "").replace("-", "")
        if q:
            entries = [
                e
                for e in entries
                if q in (e.get("user_phone") or "").replace(" ", "").replace("+", "").replace("-", "")
                or q in (e.get("user_id") or "").replace(" ", "").replace("+", "").replace("-", "")
                or q in (e.get("user_phone_masked") or "").replace(" ", "").replace("+", "").replace("-", "")
            ]
    # Normalize historical rows for the UI (honest cost status).
    out: list[dict[str, Any]] = []
    for e in entries[-limit:]:
        row = dict(e)
        if "cost_status" not in row or not row.get("cost_status"):
            row["cost_status"] = _derive_cost_status(
                source=str(row.get("source") or ""),
                cost_usd=row.get("cost_usd") if isinstance(row.get("cost_usd"), (int, float)) else None,
                prompt_tokens=row.get("prompt_tokens") if isinstance(row.get("prompt_tokens"), int) else None,
                completion_tokens=row.get("completion_tokens")
                if isinstance(row.get("completion_tokens"), int)
                else None,
                tokens=row.get("tokens") if isinstance(row.get("tokens"), int) else None,
                cost_status=None,
                ai_called=None,
            )
        if "channel" not in row or not row.get("channel"):
            row["channel"] = "unknown"
        if "direction" not in row or not row.get("direction"):
            row["direction"] = "inbound"
        out.append(row)
    return out


def clear_flows() -> None:
    """Clear flow buffer."""
    _FLOW_BUFFER.clear()
