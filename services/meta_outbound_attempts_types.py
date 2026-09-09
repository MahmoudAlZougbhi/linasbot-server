"""Types, constants, and task-local purpose helpers for Meta outbound attempts."""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Literal

from services.meta_controlled_evidence import MetaEvidenceSurface
from services.meta_outbound_purposes import ALLOWED_PURPOSES as _ALLOWED_PURPOSES
from services.meta_outbound_purposes import MetaOutboundPurpose

_EVENT_ID_RE = re.compile(r"ibe_[0-9a-f]{40}")
_ALLOWED_SURFACES = frozenset({"facebook_dm", "instagram_dm", "facebook_comment", "instagram_comment"})
_COLLECTION = "meta_outbound_attempts"
_APP_DOCUMENT = "linas-ai-bot-backend"
_MAX_TRANSACTION_ATTEMPTS = 5
_PURPOSE_DOCUMENT_DOMAIN = "meta-outbound-purpose-v1"
_IMAGE_QUOTA_NOTICE_DOMAIN = "meta-image-quota-notice-v1"
_MAX_IMAGE_QUOTA_NOTICE_BYTES = 1_000
_SHA256_RE = re.compile(r"[0-9a-f]{64}")

AttemptDecisionKind = Literal[
    "send",
    "quota_reserved",
    "duplicate_suppressed",
    "needs_owner_action",
    "nonproduction_bypass",
]
ImageQuotaDisposition = Literal["allowed", "blocked", "truncated"]
ImageQuotaPhase = Literal["reserved", "consumed", "provider"]
MetaOutboundAttemptStatus = Literal[
    "sending",
    "accepted",
    "definitive_failure",
    "needs_owner_action",
]
_ALLOWED_QUOTA_DISPOSITIONS = frozenset({"allowed", "blocked", "truncated"})
_ALLOWED_QUOTA_PHASES = frozenset({"reserved", "consumed", "provider"})
_ALLOWED_STATUSES = frozenset({"sending", "accepted", "definitive_failure", "needs_owner_action"})
_SEND_PURPOSE: ContextVar[MetaOutboundPurpose] = ContextVar(
    "meta_outbound_send_purpose",
    default="primary_reply",
)


class MetaOutboundAttemptStoreError(RuntimeError):
    """The shared at-most-once store could not be trusted."""


@dataclass(frozen=True)
class MetaOutboundAttemptDecision:
    kind: AttemptDecisionKind
    event_id: str
    surface: MetaEvidenceSurface
    purpose: MetaOutboundPurpose = "primary_reply"
    image_quota_disposition: str = ""
    image_quota_allowed_amount: int = 0
    image_quota_phase: str = ""
    image_quota_notice_text: str = field(default="", repr=False)
    image_quota_notice_sha256: str = ""
    attempt_token: str = ""
    attempt_sequence: int = 0
    binding_id: str = field(default="", repr=False)


@dataclass(frozen=True)
class MetaOutboundAttemptReceipt:
    event_id: str
    surface: MetaEvidenceSurface
    purpose: MetaOutboundPurpose
    status: MetaOutboundAttemptStatus
    image_quota_disposition: str = ""
    image_quota_allowed_amount: int = 0
    image_quota_phase: str = ""
    image_quota_notice_text: str = field(default="", repr=False)
    image_quota_notice_sha256: str = ""
    attempt_sequence: int = 0


def current_meta_outbound_send_purpose() -> MetaOutboundPurpose:
    return _SEND_PURPOSE.get()


def _validate_purpose(purpose: MetaOutboundPurpose | str) -> MetaOutboundPurpose:
    value = str(purpose or "").strip().lower()
    if value not in _ALLOWED_PURPOSES:
        raise ValueError("Meta outbound purpose is invalid")
    return value  # type: ignore[return-value]


@contextmanager
def meta_outbound_send_purpose(purpose: MetaOutboundPurpose | str) -> Iterator[None]:
    """Set one task-local semantic send role without changing SendFunc APIs."""

    safe_purpose = _validate_purpose(purpose)
    if safe_purpose == "image_quota_notice":
        raise ValueError("Image-quota notice purpose is reserved for its guarded path")
    token = _SEND_PURPOSE.set(safe_purpose)
    try:
        yield
    finally:
        _SEND_PURPOSE.reset(token)
