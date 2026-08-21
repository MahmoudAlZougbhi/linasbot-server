from __future__ import annotations

import pytest

from services.firestore_transaction_compat import run_firestore_transaction
from tests.meta_compliance_helpers import (
    _FakeFirestore,
    _GoogleLikeFirestore,
    _install_google_transactional_fake,
)


def test_run_firestore_transaction_uses_fake_commit_path() -> None:
    db = _FakeFirestore()
    app = db.collection("artifacts").document("linas-ai-bot-backend")
    ref = app.collection("inbound_events").document("evt-1")

    def _write(transaction) -> str:
        transaction.set(ref, {"state": "accepted", "revision": 1})
        return "ok"

    assert run_firestore_transaction(db, _write) == "ok"
    assert ref.get().to_dict() == {"state": "accepted", "revision": 1}


def test_run_firestore_transaction_uses_google_transactional_wrapper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _GoogleLikeFirestore()
    _install_google_transactional_fake(monkeypatch)
    app = db.collection("artifacts").document("linas-ai-bot-backend")
    ref = app.collection("inbound_events").document("evt-google")

    raw = db.transaction()
    with pytest.raises(ValueError, match="Transaction not in progress"):
        ref.get(transaction=raw)

    def _write(transaction) -> str:
        assert ref.get(transaction=transaction).exists is False
        transaction.set(ref, {"state": "accepted", "revision": 1})
        return "ok"

    assert run_firestore_transaction(db, _write) == "ok"
    assert ref.get().to_dict() == {"state": "accepted", "revision": 1}
