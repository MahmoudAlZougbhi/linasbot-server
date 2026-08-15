"""Typed Firestore conversation save outcomes for strict projection."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class FirestoreSaveStatus(StrEnum):
    CREATED = "created"
    DUPLICATE = "duplicate"
    SKIPPED = "skipped"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True)
class FirestoreSaveOutcome:
    status: FirestoreSaveStatus
    conversation_id: str | None = None
    collection: Any | None = None
