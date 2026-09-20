"""Load Live published runtime_limits with code defaults when the section is missing."""

from __future__ import annotations

from services.runtime_limits.defaults import DEFAULT_LIMITS, RuntimeLimits, clamp_payload


def load_runtime_limits(tenant_id: str | None) -> RuntimeLimits:
    """Read published CM ``runtime_limits``. Missing/unpublished → code defaults."""
    tid = (tenant_id or "").strip()
    if not tid:
        return DEFAULT_LIMITS
    try:
        from services.ai_setup.version_store import PublishedVersionError, load_published_content

        _pointer, sections = load_published_content(tid)
    except (PublishedVersionError, Exception):
        return DEFAULT_LIMITS
    raw = sections.get("runtime_limits") if isinstance(sections, dict) else None
    if not isinstance(raw, dict) or not raw:
        return DEFAULT_LIMITS
    return clamp_payload(raw)


def sanitize_runtime_limits_payload(payload: dict[str, object]) -> dict[str, object]:
    """Clamp owner-saved numbers so drafts stay valid."""
    limits = clamp_payload(payload)
    return {
        "owner_history_messages": limits.owner_history_messages,
        "owner_message_max_chars": limits.owner_message_max_chars,
        "customer_history_messages": limits.customer_history_messages,
        "customer_message_max_chars": limits.customer_message_max_chars,
        "product_search_cap": limits.product_search_cap,
        "catalog_evidence_cap": limits.catalog_evidence_cap,
        "max_retrieval_rounds": limits.max_retrieval_rounds,
        "max_agent_steps": limits.max_agent_steps,
        "max_tool_calls": limits.max_tool_calls,
    }
