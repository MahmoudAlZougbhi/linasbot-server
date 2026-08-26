"""Meta ingress must not enqueue when durable workers are not activated."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from services.meta_messaging import MetaMessagingSettings
from services.scale.inbound_event_reconcile import _enqueue_or_mark
from services.scale.meta_ingress import (
    _settings_snapshot,
    _try_enqueue,
    enqueue_meta_inbound_event,
    persist_meta_comment_accepted,
    persist_meta_dm_accepted,
)


def test_settings_snapshot_never_persists_meta_credentials() -> None:
    snapshot = _settings_snapshot(
        MetaMessagingSettings(
            enabled=True,
            app_secret="app-secret-must-not-persist",
            page_id="page-1",
            page_access_token="access-token-must-not-persist",
            instagram_account_id="ig-1",
            verify_token="verify-token-must-not-persist",
            graph_api_version="v24.0",
            app_id="app-1",
            binding_id="binding-1",
        )
    )

    assert snapshot["binding_id"] == "binding-1"
    assert snapshot["graph_api_version"] == "v24.0"
    assert "app_secret" not in snapshot
    assert "page_access_token" not in snapshot
    assert "verify_token" not in snapshot
    rendered = repr(snapshot)
    assert "must-not-persist" not in rendered


def test_try_enqueue_skips_without_redis_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LINAS_REQUIRE_REDIS", raising=False)
    monkeypatch.delenv("LINAS_ENABLE_DURABLE_QUEUES", raising=False)
    fake_queue = SimpleNamespace(backend="redis", production_ready=True, enqueue=MagicMock())
    with patch("services.job_queue.job_queue", fake_queue):
        assert _try_enqueue(event_id="evt-1", kind="meta_dm", tenant_id="linas", conversation_key="k") is None
    fake_queue.enqueue.assert_not_called()


def test_try_enqueue_when_durable_queues_activated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LINAS_REQUIRE_REDIS", "true")
    job = SimpleNamespace(id="job-1")
    fake_queue = SimpleNamespace(backend="redis", production_ready=True, enqueue=MagicMock(return_value=job))
    with patch("services.job_queue.job_queue", fake_queue):
        assert _try_enqueue(event_id="evt-2", kind="meta_dm", tenant_id="linas", conversation_key="k") == "job-1"
    fake_queue.enqueue.assert_called_once()


def _reconcile_record() -> SimpleNamespace:
    return SimpleNamespace(
        event_id="ibe_" + "9" * 40,
        kind="meta_dm",
        tenant_id="linas",
        conversation_key="linas:facebook:customer",
        attempts=1,
        claim_key="facebook:provider-mid",
    )


def test_watchdog_retains_claim_when_enqueue_ack_is_ambiguous(monkeypatch: pytest.MonkeyPatch) -> None:
    import services.job_queue as job_queue_module
    import services.scale.inbound_event_reconcile as reconcile

    monkeypatch.setattr(reconcile, "redis_required", lambda: True)
    monkeypatch.setattr(
        job_queue_module,
        "job_queue",
        SimpleNamespace(
            backend="redis",
            production_ready=True,
            enqueue=MagicMock(side_effect=TimeoutError("accepted then ack lost")),
        ),
    )
    updates: list[dict[str, object]] = []
    monkeypatch.setattr(reconcile, "mark_inbound_state", lambda *_args, **kwargs: updates.append(kwargs))
    handle = SimpleNamespace(owner_token="owner-token", generation=2)

    result = _enqueue_or_mark(_reconcile_record(), handle)

    assert result["action"] == "enqueue_ack_unknown"
    assert updates == [{"state": "queued", "last_error": "enqueue_ack_unknown"}]


def test_watchdog_retains_claim_when_post_enqueue_ledger_update_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    import services.job_queue as job_queue_module
    import services.scale.inbound_event_reconcile as reconcile

    monkeypatch.setattr(reconcile, "redis_required", lambda: True)
    monkeypatch.setattr(
        job_queue_module,
        "job_queue",
        SimpleNamespace(
            backend="redis",
            production_ready=True,
            enqueue=MagicMock(return_value=SimpleNamespace(id="job-accepted")),
        ),
    )
    monkeypatch.setattr(
        reconcile,
        "mark_inbound_state",
        MagicMock(side_effect=RuntimeError("shared ledger write failed")),
    )
    handle = SimpleNamespace(owner_token="owner-token", generation=2)

    result = _enqueue_or_mark(_reconcile_record(), handle)

    assert result == {
        "event_id": "ibe_" + "9" * 40,
        "action": "requeued_ledger_update_failed",
        "job_id": "job-accepted",
    }


@pytest.mark.parametrize("kind", ("dm", "comment"))
def test_terminal_meta_event_is_never_reopened_on_provider_redelivery(
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
) -> None:
    import services.scale.meta_ingress as ingress

    existing = SimpleNamespace(state="dead_letter", created_at=1.0, attempts=8)
    monkeypatch.setattr(ingress, "get_inbound_event", lambda _event_id: existing)
    monkeypatch.setattr(ingress, "create_inbound_event", lambda *_args, **_kwargs: (existing, False))
    monkeypatch.setattr(
        ingress,
        "_try_enqueue",
        lambda **_kwargs: pytest.fail("terminal event was re-enqueued"),
    )
    settings = MetaMessagingSettings(
        enabled=True,
        app_secret="runtime-secret",
        page_id="page-1",
        page_access_token="runtime-token",
        instagram_account_id="ig-1",
        verify_token="runtime-verify",
        graph_api_version="v24.0",
    )
    binding = SimpleNamespace(
        binding_id="binding-1",
        tenant_id="linas",
        channel="facebook",
        asset_id="page-1",
        page_id="page-1",
        instagram_account_id="ig-1",
        app_key="linas_first_party",
        auth_flow="facebook_login",
        credential_id="credential-1",
        status="active",
        generation=1,
        created_at=1.0,
        updated_at=1.0,
    )
    resolved = SimpleNamespace(
        settings=settings,
        binding=binding,
        event={
            "channel": "facebook",
            "sender_id": "customer-1",
            "message_id": "provider-event-1",
            "comment_id": "provider-comment-1",
            "text": "hello",
        },
    )

    result = (
        persist_meta_dm_accepted(resolved, global_key="facebook:provider-event-1")
        if kind == "dm"
        else persist_meta_comment_accepted(resolved, global_key="facebook:provider-comment-1")
    )

    assert result[1] is False


def test_enqueue_without_claim_handle_leaves_worker_to_adopt_lease(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        "services.scale.meta_ingress.get_inbound_event",
        lambda _event_id: SimpleNamespace(kind="meta_dm", tenant_id="linas", conversation_key="k"),
    )
    monkeypatch.setattr(
        "services.scale.meta_ingress.mark_inbound_state",
        lambda *_args, **_kwargs: None,
    )

    def fake_try_enqueue(**kwargs: object) -> str:
        captured.update(kwargs)
        return "job-queued"

    monkeypatch.setattr("services.scale.meta_ingress._try_enqueue", fake_try_enqueue)

    assert enqueue_meta_inbound_event("evt-ack", claim_handle=None) == "queued"
    assert captured["claim_token"] == ""
    assert captured["claim_generation"] == 1

