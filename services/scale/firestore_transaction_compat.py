"""Run a document transaction. Test fakes and the Postgres store both commit explicitly."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

T = TypeVar("T")


def run_firestore_transaction(db: Any, fn: Callable[[Any], T]) -> T:
    transaction = db.transaction()
    if type(transaction).__module__.startswith("google."):
        from services.persistence import query_api as gcf

        @gcf.transactional
        def _run(transaction: Any) -> T:
            return fn(transaction)

        return _run(transaction)
    result = fn(transaction)
    commit = getattr(transaction, "commit", None)
    if callable(commit):
        commit()
    return result
