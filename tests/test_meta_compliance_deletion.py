"""Authenticated Meta social-user deletion and route-inventory tests."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from services.meta_app_registry import APP_A_KEY
from services.meta_data_deletion import delete_meta_social_user_data, read_deletion_status
from tests.meta_compliance_helpers import (
    APP_A_ENV,
    APP_SECRET,
    _FakeDocument,
    _FakeFirestore,
)


@pytest.fixture(autouse=True)
def _configure_app_a(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in APP_A_ENV.items():
        monkeypatch.setenv(key, value)


def test_real_deletion_removes_namespaced_user_tree_and_index(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import config
    import services.meta_data_deletion as deletion_service
    import utils.utils

    db = _FakeFirestore()
    app = db.collection("artifacts").document("linas-ai-bot-backend")
    users = app.collection("users")
    facebook_user = users.document("facebook:123456789")
    facebook_user.exists = True
    nested = facebook_user.collection("conversations").document("conversation-1")
    nested.exists = True
    index = app.collection("live_chat_index")
    index.documents["index-1"] = _FakeDocument(
        f"{index.path}/index-1",
        data={"user_id": "facebook:123456789"},
    )
    config.user_data_whatsapp["facebook:123456789"] = {"temporary": True}

    monkeypatch.setattr(utils.utils, "get_firestore_db", lambda: db)
    monkeypatch.setattr(deletion_service, "_STATUS_DIR", tmp_path / "status")
    monkeypatch.setattr(deletion_service, "_INDEX_DIR", tmp_path / "index")

    result = delete_meta_social_user_data("123456789", APP_SECRET)

    assert result.deleted_user_documents == 1
    assert result.deleted_nested_documents == 1
    assert result.deleted_index_documents == 1
    assert facebook_user.exists is False
    assert nested.exists is False
    assert index.documents["index-1"].exists is False
    assert "facebook:123456789" not in config.user_data_whatsapp
    assert "123456789" not in result.confirmation_code
    status = read_deletion_status(result.confirmation_code)
    assert status is not None
    assert status["status"] == "completed"
    assert (tmp_path / "status" / f"{result.confirmation_code}.json").stat().st_mode & 0o777 == 0o600


def test_repeated_deletion_request_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import services.meta_data_deletion as deletion_service
    import utils.utils

    db = _FakeFirestore()
    monkeypatch.setattr(utils.utils, "get_firestore_db", lambda: db)
    monkeypatch.setattr(deletion_service, "_STATUS_DIR", tmp_path / "status")
    monkeypatch.setattr(deletion_service, "_INDEX_DIR", tmp_path / "index")

    first = delete_meta_social_user_data("123456789", APP_SECRET)
    second = delete_meta_social_user_data("123456789", APP_SECRET)
    assert first.confirmation_code == second.confirmation_code
    assert read_deletion_status(second.confirmation_code)["status"] == "no_data"


def test_tenant_namespaced_deletion_does_not_touch_unrelated_user(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import config
    import services.meta_app_registry as registry_service
    import services.meta_data_deletion as deletion_service
    import utils.utils

    db = _FakeFirestore()
    app = db.collection("artifacts").document("linas-ai-bot-backend")
    users = app.collection("users")
    tenant_user = users.document("tenant-a:facebook:123456789")
    tenant_user.exists = True
    unrelated_user = users.document("tenant-b:facebook:987654321")
    unrelated_user.exists = True
    index = app.collection("live_chat_index")
    index.documents["tenant-index"] = _FakeDocument(
        f"{index.path}/tenant-index",
        data={"user_id": "tenant-a:facebook:123456789"},
    )
    config.user_data_whatsapp["tenant-a:facebook:123456789"] = {"temporary": True}

    fake_registry = SimpleNamespace(
        list_bindings=lambda *args, **kwargs: [
            SimpleNamespace(
                app_key=APP_A_KEY,
                tenant_id="tenant-a",
                channel="facebook",
                asset_id="page-tenant-a",
            )
        ]
    )
    monkeypatch.setattr(registry_service, "get_meta_app_registry", lambda: fake_registry)
    monkeypatch.setattr(utils.utils, "get_firestore_db", lambda: db)
    monkeypatch.setattr(deletion_service, "_STATUS_DIR", tmp_path / "status")
    monkeypatch.setattr(deletion_service, "_INDEX_DIR", tmp_path / "index")

    result = delete_meta_social_user_data("123456789", APP_SECRET, app_key=APP_A_KEY)
    assert result.deleted_user_documents == 1
    assert tenant_user.exists is False
    assert unrelated_user.exists is True
    assert index.documents["tenant-index"].exists is False


def test_production_main_route_inventory_is_explicit() -> None:
    import main

    main_source = Path("main.py").read_text(encoding="utf-8")
    for route_module in (
        "modules.webhook_handlers",
        "modules.meta_messaging_webhook",
        "modules.meta_compliance",
        "modules.dashboard_api",
        "modules.auth_api",
        "modules.live_chat_api",
    ):
        assert f"import {route_module}" in main_source
    registered_paths = {getattr(route, "path", "") for route in main.app.routes}
    assert {
        "/api/health",
        "/api/ready",
        "/api/auth/login",
        "/webhook",
        "/webhook/meta-messaging",
        "/privacy-policy",
        "/terms",
        "/data-deletion",
        "/oauth/meta/deauthorize",
        "/oauth/meta/data-deletion",
        "/data-deletion/status/{confirmation_code}",
        "/meta/deauthorize",
    } <= registered_paths
