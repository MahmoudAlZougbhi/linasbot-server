"""Takeover can assign to another same-tenant staff member via existing operator_id."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from modules.live_chat_api_helpers import resolve_takeover_assignee


def test_takeover_assignee_defaults_to_session() -> None:
    session = SimpleNamespace(user_id="op-self", email="self@linas.ai", tenant_id="t1")
    operator_id, name = resolve_takeover_assignee(session, None)
    assert operator_id == "op-self"
    assert name == "self@linas.ai"


def test_takeover_assignee_same_user_skips_lookup() -> None:
    session = SimpleNamespace(user_id="op-self", email="self@linas.ai", tenant_id="t1")
    operator_id, name = resolve_takeover_assignee(session, "op-self")
    assert operator_id == "op-self"
    assert name == "self@linas.ai"


def test_takeover_assignee_other_same_tenant(monkeypatch: pytest.MonkeyPatch) -> None:
    session = SimpleNamespace(user_id="op-self", email="self@linas.ai", tenant_id="t1")

    class _Users:
        def get_user_by_id(self, user_id: str) -> dict[str, str]:
            assert user_id == "op-other"
            return {"id": "op-other", "tenantId": "t1", "name": "Mohammad Ali", "email": "m@x.com"}

    monkeypatch.setattr("services.user_service.user_service", _Users())
    operator_id, name = resolve_takeover_assignee(session, "op-other")
    assert operator_id == "op-other"
    assert name == "Mohammad Ali"


def test_takeover_assignee_rejects_other_tenant(monkeypatch: pytest.MonkeyPatch) -> None:
    session = SimpleNamespace(user_id="op-self", email="self@linas.ai", tenant_id="t1")

    class _Users:
        def get_user_by_id(self, user_id: str) -> dict[str, str]:
            return {"id": user_id, "tenantId": "other", "name": "X"}

    monkeypatch.setattr("services.user_service.user_service", _Users())
    with pytest.raises(HTTPException) as exc:
        resolve_takeover_assignee(session, "op-other")
    assert exc.value.status_code == 403


def test_takeover_assignee_missing_user(monkeypatch: pytest.MonkeyPatch) -> None:
    session = SimpleNamespace(user_id="op-self", email="self@linas.ai", tenant_id="t1")

    class _Users:
        def get_user_by_id(self, user_id: str) -> None:
            return None

    monkeypatch.setattr("services.user_service.user_service", _Users())
    with pytest.raises(HTTPException) as exc:
        resolve_takeover_assignee(session, "missing")
    assert exc.value.status_code == 400
