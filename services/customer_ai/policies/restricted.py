"""Restricted topics run before FAQ/planner. Keywords are not the only future path."""

from __future__ import annotations

from services.cm.schemas import RestrictedPolicy, RestrictedTopic
from services.cm.structured_resolver import find_restricted_topic
from services.cm.version_store import PublishedVersionError, load_published_content


def load_restricted_policy(tenant_id: str) -> RestrictedPolicy | None:
    tid = (tenant_id or "").strip()
    if not tid:
        return None
    try:
        _pointer, sections = load_published_content(tid)
    except PublishedVersionError:
        return None
    raw = sections.get("restricted")
    if not isinstance(raw, dict):
        return RestrictedPolicy()
    try:
        return RestrictedPolicy.model_validate(raw)
    except Exception:
        return RestrictedPolicy()


def find_published_restricted(tenant_id: str, message: str) -> RestrictedTopic | None:
    policy = load_restricted_policy(tenant_id)
    if policy is None:
        return None
    return find_restricted_topic(message, policy)


_DEFAULT_REFUSE = {
    "ar": "هيدا الموضوع مش من ضمن الخدمات يلي منقدمها حالياً. بس فيني ساعدك بمواضيع تانية.",
    "en": "This isn't one of the services we currently offer, but I'm happy to help with anything else.",
    "fr": "Ce sujet ne fait pas partie des services que nous proposons actuellement, mais je peux vous aider pour autre chose.",
}


def refuse_text(topic: RestrictedTopic, message: str = "") -> str:
    template = (topic.refuse_template or "").strip()
    if template:
        return template
    try:
        from services.customer_ai.greeting import inbound_greeting_language

        lang = inbound_greeting_language(message)
    except Exception:
        lang = "en"
    return _DEFAULT_REFUSE.get(lang, _DEFAULT_REFUSE["en"])
