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
