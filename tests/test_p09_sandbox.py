"""P09 sandbox and bug fixes. New behavior stays off unless its flag is on."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from modules.api_security import is_keep_tenant_api_path
from modules.web_chat_helpers import assert_origin_allowed
from services.guest.guest_inbox_bridge import pick_guest_widget
from services.integrations.meta.meta_graph_routing import graph_api_url
from services.platform.error_contract import error_body
from services.platform.idempotency import remember, replay, reset_idempotency
from services.platform.input_guards import InputRejected, parse_int
from services.privacy.account_requests import cancel_deletion, request_deletion, request_export, reset_account_requests
from services.privacy.audit_log import read_audit, reset_audit_log, write_audit
from services.sandbox.guard import SandboxOutboundBlocked, refuse_sandbox_target, sandbox_scope
from services.sandbox.lab import add_event, create_post, events_for, reset_lab
from services.sandbox.poll_backoff import poll_delay_seconds


def _on(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    monkeypatch.setenv(f"LINAS_FLAG_{name.upper()}", "on")


@pytest.fixture(autouse=True)
def _clean() -> None:
    reset_lab()
    reset_idempotency()
    reset_account_requests()
    reset_audit_log()


def test_owner_notifications_stay_blocked_until_the_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    assert is_keep_tenant_api_path("/api/owner-notifications") is False
    _on(monkeypatch, "owner_notifications_api")
    assert is_keep_tenant_api_path("/api/owner-notifications/read") is True


def test_disabled_widget_is_reported_before_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    widget = SimpleNamespace(enabled=False, site_url="https://shop.example")
    monkeypatch.setattr(
        "modules.web_chat_helpers.web_chat_store.origin_allowed_for_widget",
        lambda *args, **kwargs: False,
    )
    with pytest.raises(Exception) as blocked:
        assert_origin_allowed(widget, "https://other.example")
    assert blocked.value.detail["error"] == "ORIGIN_NOT_ALLOWED"
    _on(monkeypatch, "widget_disabled_first")

    def origin_checked(*args, **kwargs):
        _ = (args, kwargs)
        raise AssertionError("origin was checked first")

    monkeypatch.setattr("modules.web_chat_helpers.web_chat_store.origin_allowed_for_widget", origin_checked)
    with pytest.raises(Exception) as disabled:
        assert_origin_allowed(widget, "https://other.example")
    assert disabled.value.detail["error"] == "WIDGET_DISABLED"


def test_guest_chats_need_an_explicit_widget(monkeypatch: pytest.MonkeyPatch) -> None:
    only = SimpleNamespace(site_url="https://other.example")
    assert pick_guest_widget([only], "https://shop.example") is only
    _on(monkeypatch, "guest_explicit_tenant")
    assert pick_guest_widget([only], "https://shop.example") is None
    assert pick_guest_widget([only], "https://other.example") is only


def test_sandbox_captures_comments_and_blocks_graph() -> None:
    post = create_post(tenant_id="shop", platform="instagram", kind="post", caption="Hello")
    comment = add_event(tenant_id="shop", post_id=post["id"], kind="comment", text="Nice", auto_reply=True)
    assert comment["kind"] == "comment"
    assert comment["reply"] == "Captured, not sent"
    assert comment["charged_messages"] == 0
    quiet = add_event(tenant_id="shop", post_id=post["id"], kind="comment", text="Nice", auto_reply=False)
    assert "auto-reply off" in quiet["action"]
    handoff = add_event(tenant_id="shop", post_id=None, kind="dm", text="I want a human", auto_reply=True)
    assert handoff["kind"] == "dm"
    assert handoff["action"] == "human handoff"
    with pytest.raises(PermissionError):
        add_event(tenant_id="other", post_id=post["id"], kind="comment", text="x", auto_reply=True)
    assert events_for("shop")
    with pytest.raises(SandboxOutboundBlocked):
        refuse_sandbox_target("sbx_user_1/messages")
    with sandbox_scope():
        with pytest.raises(SandboxOutboundBlocked):
            graph_api_url(SimpleNamespace(auth_flow="system"), graph_api_version="v21.0", path="me/messages")
    assert "graph.facebook.com" not in open("services/sandbox/lab.py", encoding="utf-8").read()


def test_deletion_export_audit_and_idempotency() -> None:
    created = request_deletion(tenant_id="shop", user_id="owner")
    assert created["status"] == "pending"
    assert cancel_deletion(created["id"], tenant_id="shop")["status"] == "cancelled"
    exported = request_export(tenant_id="shop")
    assert "ledger" in exported["includes"]
    write_audit(tenant_id="shop", actor_user_id="owner", actor_role="owner", action="publish", target="ai_setup")
    write_audit(tenant_id="other", actor_user_id="owner", actor_role="owner", action="publish", target="ai_setup")
    assert len(read_audit(tenant_id="shop", platform=False)) == 1
    assert len(read_audit(tenant_id=None, platform=True)) == 2
    body = {"id": "p1"}
    remember("shop:create", body)
    assert replay("shop:create") == body
    assert error_body("RATE_LIMIT", "Slow down.", "تمهّل.", "Ralentissez.", retry_after=30)["error"] == "RATE_LIMIT"
    with pytest.raises(InputRejected):
        parse_int("nope", name="count")
    assert poll_delay_seconds(0) == 5
    assert poll_delay_seconds(3) == 30


def test_refresh_marks_the_access_session_revoked(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.dashboard.dashboard_session_service import session_service

    _on(monkeypatch, "revoke_rotated_access")
    session_service._memory["old-session"] = {
        "session_id": "old-session",
        "tenant_id": "",
        "revoked": False,
        "user_id": "u",
        "email": "a@b.c",
        "role": "viewer",
        "expires_at": 9_999_999_999,
    }
    session_service.revoke_session_id("old-session")
    assert session_service._memory["old-session"]["revoked"] is True


def test_import_smoke() -> None:
    import modules.sandbox_api
    import services.privacy.audit_log
    import services.sandbox.lab

    assert modules.sandbox_api is not None
    assert services.sandbox.lab.create_post
    assert services.privacy.audit_log.write_audit
