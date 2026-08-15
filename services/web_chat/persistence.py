"""Strict Firestore persistence for Website Chat with typed outcomes."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from utils.conversation_save_result import FirestoreSaveOutcome, FirestoreSaveStatus
from utils.utils import save_conversation_message_to_firestore


class PersistOutcome(StrEnum):
    CREATED = "created"
    DUPLICATE = "duplicate"
    SKIPPED = "skipped"
    AMBIGUOUS = "ambiguous"


class PersistFailure(Exception):
    def __init__(self, code: str, message: str, *, cause: BaseException | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.cause = cause


@dataclass(frozen=True)
class PersistResult:
    outcome: PersistOutcome
    conversation_id: str


def _outcome_from_save(
    saved: FirestoreSaveOutcome | tuple[str, Any] | None,
    *,
    conversation_id: str,
) -> PersistResult:
    if isinstance(saved, FirestoreSaveOutcome):
        if saved.status == FirestoreSaveStatus.CREATED:
            return PersistResult(
                outcome=PersistOutcome.CREATED,
                conversation_id=str(saved.conversation_id or conversation_id),
            )
        if saved.status == FirestoreSaveStatus.DUPLICATE:
            return PersistResult(outcome=PersistOutcome.DUPLICATE, conversation_id=conversation_id)
        if saved.status == FirestoreSaveStatus.AMBIGUOUS:
            return PersistResult(outcome=PersistOutcome.AMBIGUOUS, conversation_id=conversation_id)
        raise PersistFailure("firestore_unavailable", "Firestore persistence is unavailable.")
    if saved is None:
        raise PersistFailure("firestore_unavailable", "Firestore persistence returned no outcome.")
    conv_id = saved[0] if isinstance(saved, tuple) else conversation_id
    return PersistResult(outcome=PersistOutcome.CREATED, conversation_id=str(conv_id or conversation_id))


async def persist_web_chat_message(
    *,
    user_id: str,
    role: str,
    text: str,
    conversation_id: str,
    metadata: dict[str, Any],
) -> PersistResult:
    """Persist one message; never treat Firestore errors or skips as duplicate."""
    meta = dict(metadata or {})
    source_message_id = str(meta.get("source_message_id") or meta.get("idempotency_key") or "").strip()
    if source_message_id:
        meta.setdefault("source_message_id", source_message_id)
        meta.setdefault("idempotency_key", source_message_id)

    try:
        saved = await save_conversation_message_to_firestore(
            user_id=user_id,
            role=role,
            text=text,
            conversation_id=conversation_id,
            metadata=meta,
        )
    except Exception as exc:
        raise PersistFailure("firestore_error", "Firestore persistence failed.", cause=exc) from exc

    return _outcome_from_save(saved, conversation_id=conversation_id)
