"""Catalog audit rows record when the change happened."""

from __future__ import annotations

import time

from services.billing.membership.catalog_admin import audit_log, update_draft


def test_catalog_edit_records_created_at(monkeypatch) -> None:
    monkeypatch.setattr("services.billing.membership.catalog_admin._persist_unlocked", lambda: None)
    monkeypatch.setattr("services.billing.membership.catalog_admin._refresh_unlocked", lambda: None)
    before = time.time()
    update_draft(actor="owner", reason="portal_edit", changes={})
    row = audit_log()[-1]
    assert row["created_at"] >= before
    assert row["created_at"] <= time.time() + 5
