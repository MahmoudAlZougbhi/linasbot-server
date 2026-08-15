"""HTTP-level Web Chat API tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from services.web_chat.store import WebChatStore


async def _fake_process(**_kwargs) -> str:
    return "Hello from custom UI"


@pytest.fixture()
def web_store(tmp_path, monkeypatch):
    store = WebChatStore(root=tmp_path / "web_chat")
    monkeypatch.setattr("services.web_chat.store.web_chat_store", store)
    monkeypatch.setattr("modules.web_chat_helpers.web_chat_store", store)
    monkeypatch.setattr("modules.web_chat_public_routes.web_chat_store", store)
    monkeypatch.setattr("modules.web_chat_mobile_routes.web_chat_store", store)
    return store


@pytest.fixture()
def client(monkeypatch, web_store):
    from services import entitlements_service as es
    from services.entitlements_service import EntitlementsStore
    from services.membership import web_gate as wg

    ent = EntitlementsStore(root=web_store._root.parent / "ent")
    monkeypatch.setattr(es, "entitlements_store", ent)
    monkeypatch.setattr(wg, "entitlements_store", ent)
    ent.set_plan(tenant_id="biz", plan_id="max", status="active", source="admin")

    from main import app

    return TestClient(app)


def _seed_widget(store: WebChatStore) -> tuple[str, str]:
    widget = store.update_widget(
        "biz",
        site_url="https://shop.example.com",
        enabled=True,
        integration_mode="linas_widget",
    )
    return widget.widget_key, widget.tenant_id


def test_public_config_and_heartbeat(client, web_store, monkeypatch) -> None:
    key, _tid = _seed_widget(web_store)
    monkeypatch.setattr(
        "services.web_chat.processor.evaluate_web_ai_eligibility",
        lambda *_a, **_k: (True, None),
    )

    cfg = client.get(
        f"/api/web-chat/config?widget_key={key}",
        headers={"Origin": "https://shop.example.com"},
    )
    assert cfg.status_code == 200
    body = cfg.json()
    assert body["success"] is True
    assert body["config"]["integration_mode"] == "linas_widget"
    assert body["config"]["appearance"]["identity"]["display_name"]

    hb = client.post(
        "/api/web-chat/heartbeat",
        json={"widget_key": key},
        headers={"Origin": "https://www.shop.example.com"},
    )
    assert hb.status_code == 200
    updated = web_store.get_widget_by_key(key)
    assert updated is not None
    assert updated.installation.last_seen_at is not None


def test_origin_reject_and_allow_www(client, web_store) -> None:
    key, _tid = _seed_widget(web_store)
    bad = client.post(
        "/api/web-chat/session",
        json={"visitor_session_id": "visitor123456", "widget_key": key},
        headers={"Origin": "https://evil.example"},
    )
    assert bad.status_code == 403

    ok = client.post(
        "/api/web-chat/session",
        json={"visitor_session_id": "visitor123456", "widget_key": key},
        headers={"Origin": "https://www.shop.example.com"},
    )
    assert ok.status_code == 200
    assert ok.json()["channel"] == "web"


def test_custom_chat_mode_still_reports_web_channel(client, web_store, monkeypatch) -> None:
    key, _tid = _seed_widget(web_store)
    web_store.update_widget("biz", integration_mode="custom_chat")
    monkeypatch.setattr(
        "services.web_chat.processor.evaluate_web_ai_eligibility",
        lambda *_a, **_k: (True, None),
    )
    monkeypatch.setattr(
        "modules.web_chat_public_routes.process_web_chat_message",
        _fake_process,
    )

    session = client.post(
        "/api/web-chat/session",
        json={"visitor_session_id": "visitor99999999", "widget_key": key},
        headers={"Origin": "https://shop.example.com"},
    )
    assert session.status_code == 200

    msg = client.post(
        "/api/web-chat/session/messages",
        json={
            "visitor_session_id": "visitor99999999",
            "widget_key": key,
            "content": "Need pricing",
        },
        headers={"Origin": "https://shop.example.com"},
    )
    assert msg.status_code == 200
    assert msg.json()["channel"] == "web"
    assert msg.json()["reply"] == "Hello from custom UI"


def test_mobile_payload_includes_mode_and_installation(client, web_store, monkeypatch) -> None:
    key, _tid = _seed_widget(web_store)
    web_store.record_installation_heartbeat(
        web_store.get_widget_by_key(key),  # type: ignore[arg-type]
        origin="https://shop.example.com",
    )
    monkeypatch.setattr(
        "services.web_chat.processor.evaluate_web_ai_eligibility",
        lambda *_a, **_k: (True, None),
    )

    from services.dashboard_session_service import SESSION_COOKIE_NAME, session_service

    session = session_service.create_session(
        user_id="u-web",
        email="web@example.com",
        role="admin",
        permissions=None,
        tenant_id="biz",
    )
    token = session_service.cookie_value_for(session)

    res = client.get("/api/mobile/web-chat", cookies={SESSION_COOKIE_NAME: token})
    assert res.status_code == 200
    payload = res.json()["web_chat"]
    assert payload["integration_mode"] == "linas_widget"
    assert payload["membership_allows"] is True
    assert payload["installation"]["installed"] is True
    assert payload["installation_status"] in {"connected", "waiting", "domain_mismatch", "disabled"}


def test_legacy_widget_without_appearance_gets_defaults(web_store) -> None:
    widget = web_store.get_or_create_widget("legacy")
    raw_path = web_store._tenant_path("legacy")
    raw_path.write_text(
        '{"tenant_id":"legacy","widget_key":"k123456789012345678901234","site_url":"","enabled":false,'
        '"created_at":1,"updated_at":1}',
        encoding="utf-8",
    )
    loaded = web_store.get_or_create_widget("legacy")
    assert loaded.appearance["theme"]["mode"] == "light"
    assert loaded.integration_mode == "linas_widget"


def test_widget_disabled_blocks_config(client, web_store) -> None:
    widget = web_store.update_widget("biz", site_url="https://shop.example.com", enabled=False)
    res = client.get(f"/api/web-chat/config?widget_key={widget.widget_key}")
    assert res.status_code == 403
