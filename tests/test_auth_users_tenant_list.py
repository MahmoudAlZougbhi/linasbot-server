"""Tenant user listing must survive legacy rows and return scoped members."""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import MagicMock

import pytest
from starlette.requests import Request

from modules import auth_users_api
from modules.api_security import resolve_permissions
from services.dashboard_session_service import SessionRecord
from services.user_service import UserService


def _doc(doc_id: str, data: dict[str, Any]) -> MagicMock:
    doc = MagicMock()
    doc.id = doc_id
    doc.to_dict.return_value = data
    return doc


def _request(tenant_id: str = "linas") -> Request:
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/auth/users",
            "query_string": b"",
            "headers": [],
        }
    )
    request.state.dashboard_session = SessionRecord(
        session_id="session-linas",
        user_id="owner-1",
        email="owner@linas.test",
        role="owner",
        permissions=None,
        tenant_id=tenant_id,
        csrf_token="csrf",
        created_at=time.time(),
        expires_at=time.time() + 3600,
    )
    return request


def test_sanitize_user_skips_missing_tenant_and_uses_doc_id() -> None:
    svc = UserService()
    assert svc._sanitize_user({"email": "orphan@test.com"}, doc_id="doc-orphan") is None
    out = svc._sanitize_user(
        {"email": "member@test.com", "role": "operator", "tenant_id": "linas"},
        doc_id="doc-member",
    )
    assert out is not None
    assert out["id"] == "doc-member"
    assert out["tenantId"] == "linas"


def _mock_collection(svc: UserService, monkeypatch: pytest.MonkeyPatch, coll: MagicMock) -> None:
    mock_db = MagicMock()
    mock_db.collection.return_value.document.return_value.collection.return_value = coll
    monkeypatch.setattr(svc, "_db", mock_db)


def test_get_users_for_tenant_queries_both_tenant_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    svc = UserService()
    docs_by_field = {
        "tenantId": [
            _doc(
                "u-admin",
                {"email": "admin@linas.test", "role": "admin", "tenantId": "linas", "status": "active"},
            ),
        ],
        "tenant_id": [
            _doc(
                "u-operator",
                {"email": "op@linas.test", "role": "operator", "tenant_id": "linas", "status": "active"},
            ),
        ],
    }

    def _where(*, filter: Any) -> MagicMock:
        field = filter.field_path
        value = filter.value
        q = MagicMock()
        q.stream.side_effect = lambda **_kwargs: iter(docs_by_field[field])
        return q

    _mock_collection(svc, monkeypatch, MagicMock(where=_where))

    users = svc.get_users_for_tenant("linas")
    assert {u["id"] for u in users} == {"u-admin", "u-operator"}


def test_get_all_users_skips_bad_rows_instead_of_emptying_list(monkeypatch: pytest.MonkeyPatch) -> None:
    svc = UserService()
    docs = [
        _doc("bad", {"email": "bad@test.com", "role": "viewer"}),
        _doc(
            "good",
            {"email": "good@test.com", "role": "admin", "tenantId": "linas", "status": "active"},
        ),
    ]
    _mock_collection(svc, monkeypatch, MagicMock(stream=lambda **_kwargs: iter(docs)))

    users = svc.get_all_users()
    assert len(users) == 1
    assert users[0]["id"] == "good"


@pytest.mark.asyncio
async def test_get_users_endpoint_uses_tenant_scoped_query(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [
        {"id": "u1", "email": "a@linas.test", "role": "admin", "tenantId": "linas"},
        {"id": "u2", "email": "b@linas.test", "role": "operator", "tenantId": "linas"},
    ]
    monkeypatch.setattr(auth_users_api.user_service, "get_users_for_tenant", lambda tenant_id: rows)

    response = await auth_users_api.get_users(_request())

    assert response == {"success": True, "users": rows}


def test_owner_role_resolves_user_management_permission() -> None:
    perms = resolve_permissions("owner", None)
    assert perms["userManagement"] is True
