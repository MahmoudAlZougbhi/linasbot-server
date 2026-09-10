"""Test adapter: persist an approved envelope without channel send."""

from __future__ import annotations

from dataclasses import dataclass, field

from services.customer_ai.contracts.reply import FinalReplyEnvelope

_SAVED: list["SavedOutbound"] = []


@dataclass(frozen=True)
class SavedOutbound:
    envelope: FinalReplyEnvelope
    persisted: bool = True
    sent: bool = False
    extra: dict = field(default_factory=dict)


def reset_saved_outbox() -> None:
    _SAVED.clear()


def save_envelope_for_test(envelope: FinalReplyEnvelope, **extra: object) -> SavedOutbound:
    saved = SavedOutbound(envelope=envelope, persisted=True, sent=False, extra=dict(extra))
    _SAVED.append(saved)
    return saved


def saved_outbox() -> list[SavedOutbound]:
    return list(_SAVED)
