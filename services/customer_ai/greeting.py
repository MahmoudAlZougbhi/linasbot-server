"""One server-owned greeting eligibility policy.

Maps the existing 12-hour inactivity window (`CONTEXT_WINDOW_HOURS`) instead of
silently inventing a new threshold.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import config
from services.cm.schemas import DynamicMessageRecord, DynamicMessagesSection
from services.cm.version_store import PublishedVersionError, load_published_content
from services.customer_ai.contracts.turn import HistorySnapshot
from services.customer_ai.normalize import normalize_search_text


@dataclass(frozen=True)
class GreetingDecision:
    eligible: bool
    text: str = ""
    rule_id: str = ""
    reason: str = ""


def inactivity_threshold() -> timedelta:
    """Use the existing Meta DM 12-hour constant; do not invent a new window."""
    try:
        from handlers.text_handlers_message_greeting import GREETING_INACTIVITY_SECONDS

        seconds = int(GREETING_INACTIVITY_SECONDS)
        if seconds > 0:
            return timedelta(seconds=seconds)
    except Exception:
        pass
    hours = int(getattr(config, "CONTEXT_WINDOW_HOURS", 12) or 12)
    return timedelta(hours=max(hours, 0))


def load_dynamic_messages(tenant_id: str) -> DynamicMessagesSection | None:
    try:
        _pointer, sections = load_published_content(tenant_id)
    except PublishedVersionError:
        return None
    raw = sections.get("dynamic_messages") or sections.get("greetings")
    if not isinstance(raw, dict):
        return None
    try:
        return DynamicMessagesSection.model_validate(raw)
    except Exception:
        return None


def _rule_text(rule: DynamicMessageRecord, language: str) -> str:
    lang = (language or "ar").strip().lower()
    for key in (lang, "ar", "en", "fr"):
        value = str(getattr(rule, key, "") or "").strip()
        if value:
            return value
    return ""


def inbound_greeting_language(message: str) -> str:
    text = (message or "").strip()
    if not text:
        return "en"
    try:
        from services.system_knowledge_retrieval import detect_message_language

        code = detect_message_language(text, fallback="en")
        if code in {"ar", "franco"}:
            return "ar"
        if code in {"en", "fr"}:
            return code
    except Exception:
        pass
    return "en"


def _greeting_texts(section: DynamicMessagesSection) -> set[str]:
    texts: set[str] = set()
    for rule in section.items:
        if not rule.enabled:
            continue
        for lang in ("ar", "en", "fr"):
            value = str(getattr(rule, lang, "") or "").strip()
            if value:
                texts.add(value)
    return texts


def _history_already_greeted(
    history: HistorySnapshot,
    section: DynamicMessagesSection,
    now: datetime,
) -> bool:
    if _session_start(history, now):
        return False
    texts = _greeting_texts(section)
    if not texts:
        return False
    return any(
        item.role in {"assistant", "ai", "bot"} and (item.text or "").strip() in texts for item in history.messages
    )


def _trigger_ok(rule: DynamicMessageRecord, message: str, *, session_start: bool) -> bool:
    mode = (rule.trigger_mode or "always").strip().lower()
    if mode == "always":
        return session_start
    if mode == "session_start":
        return session_start
    hay = message or ""
    if mode == "starts_with":
        needle = (rule.trigger_pattern or "").strip()
        return bool(needle) and hay.lower().startswith(needle.lower())
    if mode == "any_keyword":
        return any(
            normalize_search_text(k) and normalize_search_text(k) in normalize_search_text(hay) for k in rule.keywords
        )
    return False


def _session_start(history: HistorySnapshot, now: datetime) -> bool:
    visible_user = [m for m in history.messages if m.role in {"user", "customer"}]
    if len(visible_user) <= 1:
        return True
    previous = [m for m in visible_user if not m.is_current_inbound]
    if not previous:
        return True
    last = previous[-1]
    if not last.timestamp:
        return False
    try:
        parsed = datetime.fromisoformat(last.timestamp.replace("Z", "+00:00"))
    except ValueError:
        return False
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return now - parsed >= inactivity_threshold()


def evaluate_greeting(
    *,
    tenant_id: str,
    message: str,
    history: HistorySnapshot,
    language: str = "",
    already_greeted: bool = False,
    invocation_kind: str = "dm",
    now: datetime | None = None,
) -> GreetingDecision:
    if invocation_kind in {"followup", "comment"} or already_greeted:
        return GreetingDecision(False, reason="not_eligible")
    section = load_dynamic_messages(tenant_id)
    if section is None:
        return GreetingDecision(False, reason="no_greeting_config")
    current = now or datetime.now(UTC)
    if _history_already_greeted(history, section, current):
        return GreetingDecision(False, reason="already_greeted")
    session_start = _session_start(history, current)
    language = (language or inbound_greeting_language(message)).strip().lower() or "en"
    for rule in section.items:
        if not rule.enabled:
            continue
        if not _trigger_ok(rule, message, session_start=session_start):
            continue
        text = _rule_text(rule, language)
        if not text:
            continue
        return GreetingDecision(True, text=text, rule_id=rule.id, reason="matched")
    return GreetingDecision(False, reason="no_match")
