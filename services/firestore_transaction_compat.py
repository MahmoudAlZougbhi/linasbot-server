"""Run Firestore transactions with google-cloud-firestore 2.x @transactional semantics."""

from __future__ import annotations

from typing import Any, Callable, TypeVar

T = TypeVar("T")


def run_firestore_transaction(db: Any, fn: Callable[[Any], T]) -> T:
    """Execute ``fn(transaction)`` using the SDK-correct transactional wrapper.

    google-cloud-firestore 2.x rejects manual ``transaction.commit()`` after
    ``ref.get(transaction=...)`` with ``Transaction not in progress``. The
    ``@firestore.transactional`` decorator is required for real clients. Test
    fakes keep the legacy commit path.
    """

    transaction = db.transaction()
    if type(transaction).__module__.startswith("google."):
        from google.cloud import firestore as gcf

        @gcf.transactional
        def _run(transaction: Any) -> T:
            return fn(transaction)

        return _run(transaction)
    result = fn(transaction)
    transaction.commit()
    return result
