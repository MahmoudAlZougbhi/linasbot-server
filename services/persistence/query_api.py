"""Small stand-in for the query types callers used to import from the Firestore SDK."""

from __future__ import annotations

from typing import Any


class Query:
    DESCENDING = "DESCENDING"
    ASCENDING = "ASCENDING"


class FieldFilter:
    def __init__(self, field: str, op: str, value: Any) -> None:
        self.field_path = field
        self.op_string = op
        self.value = value


class Increment:
    def __init__(self, value: int | float) -> None:
        self.value = value


class AlreadyExists(Exception):
    """Raised when create() hits a row that is already stored."""


SERVER_TIMESTAMP = object()


def transactional(fn: Any) -> Any:
    """Default wrapper. Tests replace this for the SDK-like transaction fake."""

    def _run(transaction: Any, *args: Any, **kwargs: Any) -> Any:
        return fn(transaction, *args, **kwargs)

    return _run
