"""Direct tests for mobile refresh token tenant requirements."""

from __future__ import annotations

import json

import pytest

from services.mobile_refresh_token_service import (
    MobileRefreshRecord,
    MobileRefreshTokenService,
    _hash_token,
)


def test_issue_explicit_linas_tenant(tmp_path) -> None:
    svc = MobileRefreshTokenService(store_dir=tmp_path / "refresh")
    raw = svc.issue(user_id="u1", email="a@b.com", tenant_id="linas", session_id="s1")
    rec = svc.consume(raw)
    assert rec is not None
    assert rec.tenant_id == "linas"


@pytest.mark.parametrize("tenant_id", [None, "", "   ", "\t"])
def test_issue_rejects_missing_tenant(tmp_path, tenant_id: str | None) -> None:
    svc = MobileRefreshTokenService(store_dir=tmp_path / "refresh")
    with pytest.raises(ValueError, match="tenant_id required"):
        svc.issue(user_id="u1", email="a@b.com", tenant_id=tenant_id, session_id="s1")


@pytest.mark.parametrize("tenant_id", [None, "", "   "])
def test_from_dict_rejects_missing_tenant(tenant_id: str | None) -> None:
    with pytest.raises(ValueError, match="tenant_id required"):
        MobileRefreshRecord.from_dict(
            {
                "user_id": "u1",
                "tenant_id": tenant_id,
                "created_at": 1.0,
                "expires_at": 2.0,
            }
        )


def test_from_dict_accepts_explicit_linas() -> None:
    rec = MobileRefreshRecord.from_dict(
        {
            "user_id": "u1",
            "tenant_id": "linas",
            "created_at": 1.0,
            "expires_at": 2.0,
        }
    )
    assert rec.tenant_id == "linas"


def test_consume_rejects_stored_record_missing_tenant(tmp_path) -> None:
    svc = MobileRefreshTokenService(store_dir=tmp_path / "refresh")
    raw = svc.issue(user_id="u1", email="a@b.com", tenant_id="t1", session_id="s1")
    path = svc._path(_hash_token(raw))
    data = json.loads(path.read_text(encoding="utf-8"))
    del data["tenant_id"]
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ValueError, match="tenant_id required"):
        svc.consume(raw)
