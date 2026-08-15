"""PII-safe runtime markers for correlated Meta controlled tests.

Only the stable inbound-event digest and fixed allowlisted values may cross this
logging boundary.  Provider identifiers, asset identifiers, and message/comment
content are deliberately not accepted by this API.
"""

from __future__ import annotations

import logging
import re
from typing import Final, Literal

MetaEvidenceSurface = Literal[
    "facebook_dm",
    "instagram_dm",
    "facebook_comment",
    "instagram_comment",
]
MetaEvidenceOutcome = Literal[
    "instagram_login_authenticated",
    "provider_accepted",
    "duplicate_suppressed",
    "retry",
    "failed",
    "second_send",
]

_EVENT_ID_RE: Final[re.Pattern[str]] = re.compile(r"ibe_[0-9a-f]{40}")
_SURFACES: Final[frozenset[str]] = frozenset({"facebook_dm", "instagram_dm", "facebook_comment", "instagram_comment"})
_OUTCOMES: Final[frozenset[str]] = frozenset(
    {
        "instagram_login_authenticated",
        "provider_accepted",
        "duplicate_suppressed",
        "retry",
        "failed",
        "second_send",
    }
)


def meta_evidence_surface(*, kind: str, channel: str) -> MetaEvidenceSurface | None:
    """Return an allowlisted surface without reflecting untrusted input."""

    normalized_kind = str(kind).strip().lower()
    normalized_channel = str(channel).strip().lower()
    if normalized_kind == "meta_dm" and normalized_channel == "facebook":
        return "facebook_dm"
    if normalized_kind == "meta_dm" and normalized_channel == "instagram":
        return "instagram_dm"
    if normalized_kind == "meta_comment" and normalized_channel == "facebook":
        return "facebook_comment"
    if normalized_kind == "meta_comment" and normalized_channel == "instagram":
        return "instagram_comment"
    return None


def log_meta_controlled_evidence(
    logger: logging.Logger,
    *,
    event_id: str,
    surface: MetaEvidenceSurface | str | None,
    outcome: MetaEvidenceOutcome | str,
) -> bool:
    """Emit one fixed-shape marker, or a fully redacted rejection warning.

    Returning ``False`` lets callers/tests detect an invalid correlation value.
    The rejected value itself is never interpolated into a log message.
    """

    safe_event_id = str(event_id).strip().lower()
    safe_surface = str(surface or "").strip().lower()
    safe_outcome = str(outcome).strip().lower()
    if _EVENT_ID_RE.fullmatch(safe_event_id) is None or safe_surface not in _SURFACES or safe_outcome not in _OUTCOMES:
        logger.warning("[meta-evidence-v2] marker_rejected reason=invalid_fixed_field")
        return False
    logger.info(
        "[meta-evidence-v2] event surface=%s outcome=%s event_id=%s",
        safe_surface,
        safe_outcome,
        safe_event_id,
    )
    return True
