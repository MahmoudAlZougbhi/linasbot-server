from __future__ import annotations

from services.firestore_transaction_compat import run_firestore_transaction
from tests.meta_compliance_helpers import _FakeFirestore


def test_run_firestore_transaction_uses_fake_commit_path() -> None:
    db = _FakeFirestore()
    app = db.collection("artifacts").document("linas-ai-bot-backend")
    ref = app.collection("inbound_events").document("evt-1")

    def _write(transaction) -> str:
        transaction.set(ref, {"state": "accepted", "revision": 1})
        return "ok"

    assert run_firestore_transaction(db, _write) == "ok"
    assert ref.get().to_dict() == {"state": "accepted", "revision": 1}
