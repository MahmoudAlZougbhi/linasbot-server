"""Restricted Topics catalog helpers. Migration museum is gone."""

from __future__ import annotations

from services.ai_setup.constants import INITIAL_RESTRICTED_LABELS, INITIAL_RESTRICTED_TOPIC_IDS
from services.ai_setup.schemas import initial_restricted_policy


def test_initial_restricted_catalog_is_empty() -> None:
    assert INITIAL_RESTRICTED_TOPIC_IDS == ()
    assert INITIAL_RESTRICTED_LABELS == {}
    inactive = initial_restricted_policy()
    assert inactive.topics == []
    active = initial_restricted_policy(active=True)
    assert active.topics == []
