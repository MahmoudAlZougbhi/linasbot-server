"""Queue outcomes keep retryable Meta deliveries non-terminal."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from typing import Any

import pytest

from services.meta_app_registry import MetaAssetBinding
from services.meta_comment_replies import CommentReplyResult
from services.meta_messaging import MetaMessagingSettings
from services.queues.meta_inbound_handler import handle_meta_inbound_process
from services.queues.models import QueueJob


@pytest.fixture(autouse=True)
def _owned_claim(monkeypatch: pytest.MonkeyPatch) -> None:
    import services.durable_event_claim as claims

    handle = SimpleNamespace(
        owner_token="test-owner-token-" + "x" * 32,
        generation=1,
        nonproduction_bypass=True,
    )

    async def acquire(*_args: Any, **_kwargs: Any) -> Any:
        return handle

    async def renew(*_args: Any, **_kwargs: Any) -> bool:
        return True

    async def run(*_args: Any, operation: Any, **_kwargs: Any) -> Any:
        return await operation()

    monkeypatch.setattr(claims, "try_claim_event_handle", acquire)
    monkeypatch.setattr(claims, "renew_event_claim", renew)
    monkeypatch.setattr(claims, "run_under_event_claim", run)


def _settings() -> MetaMessagingSettings:
    return MetaMessagingSettings(
        enabled=True,
        app_secret="runtime-secret",
        page_id="page-1",
        page_access_token="runtime-token",
        instagram_account_id="",
        verify_token="runtime-verify",
        graph_api_version="v24.0",
    )


def _record() -> SimpleNamespace:
    return SimpleNamespace(
        event_id="event-comment-1",
        kind="meta_comment",
        tenant_id="linas",
        state="accepted",
        claim_key="claim-comment-1",
        payload={"comment_id": "comment-1", "text": "hello", "author_id": "customer-1"},
        settings_snapshot={"binding_id": "binding-1"},
        binding_snapshot={
            "binding_id": "binding-1",
            "tenant_id": "linas",
            "channel": "facebook",
            "asset_id": "page-1",
            "page_id": "page-1",
            "app_key": "linas_first_party",
            "credential_id": "credential-1",
            "status": "active",
            "generation": 1,
        },
    )


def _dm_record() -> SimpleNamespace:
    record = _record()
    record.event_id = "event-dm-1"
    record.kind = "meta_dm"
    record.claim_key = "claim-dm-1"
    record.payload = {"message_id": "message-1", "sender_id": "customer-1", "text": "hello"}
    return record


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal_state", ("completed", "dead_letter"))
async def test_terminal_event_is_never_rehydrated_or_reprocessed(
    monkeypatch: pytest.MonkeyPatch,
    terminal_state: str,
) -> None:
    import services.queues.meta_inbound_handler as handler

    record = _dm_record()
    record.state = terminal_state
    monkeypatch.setattr(handler, "get_inbound_event", lambda _event_id: record)
    monkeypatch.setattr(
        handler,
        "mark_inbound_state",
        lambda *_args, **_kwargs: pytest.fail("terminal event was mutated"),
    )
    monkeypatch.setattr(
        handler,
        "_settings_from_snapshot",
        lambda *_args: pytest.fail("terminal payload was rehydrated"),
    )
    job = QueueJob.new(
        queue="high_priority",
        job_type="meta_inbound_process",
        tenant_id="linas",
        payload={"event_id": record.event_id, "kind": record.kind},
    )

    result = await handle_meta_inbound_process(job)

    assert result == {
        "skipped": True,
        "reason": f"already_{terminal_state}",
        "event_id": record.event_id,
    }


def test_legacy_rehydration_ignores_plaintext_secrets_in_old_ledger_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import services.queues.meta_inbound_handler as handler

    live = _settings()
    monkeypatch.setattr("services.meta_messaging.get_meta_messaging_settings", lambda: live)
    resolved = handler._settings_from_snapshot(
        {
            "binding_id": "legacy-single-app",
            "app_secret": "stale-ledger-secret",
            "page_access_token": "stale-ledger-token",
            "verify_token": "stale-ledger-verify",
        },
        {"binding_id": "legacy-single-app"},
    )

    assert resolved is live
    assert resolved.page_access_token == "runtime-token"


def _registry_binding(
    binding_id: str,
    *,
    status: str,
    previous_binding_id: str = "",
    tenant_id: str = "linas",
    asset_id: str = "ig-1",
) -> MetaAssetBinding:
    return MetaAssetBinding(
        binding_id=binding_id,
        tenant_id=tenant_id,
        channel="instagram",
        asset_id=asset_id,
        page_id="",
        instagram_account_id=asset_id,
        app_key="linas_first_party",
        credential_id=f"credential-{binding_id}",
        status=status,  # type: ignore[arg-type]
        generation=1,
        created_at=1.0,
        updated_at=1.0,
        previous_binding_id=previous_binding_id,
        auth_flow="instagram_login",
    )


def test_queued_event_follows_strict_reauth_replacement_chain(monkeypatch: pytest.MonkeyPatch) -> None:
    import services.queues.meta_inbound_handler as handler

    old = _registry_binding("old", status="inactive")
    middle = _registry_binding("middle", status="inactive", previous_binding_id="old")
    active = _registry_binding("active", status="active", previous_binding_id="middle")
    registry = SimpleNamespace(
        list_bindings=lambda **_kwargs: [old, middle, active],
    )
    monkeypatch.setattr("services.meta_app_registry.get_meta_app_registry", lambda: registry)

    resolved = handler._resolve_active_registry_binding(
        {"binding_id": "old"},
        {
            "binding_id": "old",
            "tenant_id": "linas",
            "channel": "instagram",
            "asset_id": "ig-1",
            "app_key": "linas_first_party",
            "auth_flow": "instagram_login",
        },
    )

    assert resolved is active


def test_queued_event_follows_strict_chain_back_after_rollback(monkeypatch: pytest.MonkeyPatch) -> None:
    import services.queues.meta_inbound_handler as handler

    rolled_back = _registry_binding("old", status="active")
    rejected_new = _registry_binding("new", status="inactive", previous_binding_id="old")
    registry = SimpleNamespace(list_bindings=lambda **_kwargs: [rolled_back, rejected_new])
    monkeypatch.setattr("services.meta_app_registry.get_meta_app_registry", lambda: registry)

    resolved = handler._resolve_active_registry_binding(
        {"binding_id": "new"},
        {
            "binding_id": "new",
            "tenant_id": "linas",
            "channel": "instagram",
            "asset_id": "ig-1",
            "app_key": "linas_first_party",
            "auth_flow": "instagram_login",
        },
    )

    assert resolved is rolled_back


def test_queued_event_rejects_replacement_crossing_tenant_or_asset(monkeypatch: pytest.MonkeyPatch) -> None:
    import services.queues.meta_inbound_handler as handler

    old = _registry_binding("old", status="inactive")
    wrong = _registry_binding(
        "wrong",
        status="active",
        previous_binding_id="old",
        tenant_id="other",
        asset_id="other-ig",
    )
    registry = SimpleNamespace(list_bindings=lambda **_kwargs: [old, wrong])
    monkeypatch.setattr("services.meta_app_registry.get_meta_app_registry", lambda: registry)

    with pytest.raises(Exception, match="no unique active replacement"):
        handler._resolve_active_registry_binding(
            {"binding_id": "old"},
            {
                "binding_id": "old",
                "tenant_id": "linas",
                "channel": "instagram",
                "asset_id": "ig-1",
                "app_key": "linas_first_party",
                "auth_flow": "instagram_login",
            },
        )


@pytest.mark.asyncio
async def test_queue_uses_snapshot_a_for_outbound_authority_with_replacement_b_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import services.queues.meta_inbound_handler as handler
    import utils.utils
    from services import meta_outbound_attempts as attempts
    from services.meta_claim_data_deletion import build_shared_meta_claim_deletion_plan
    from tests.meta_compliance_helpers import _FakeFirestore

    db = _FakeFirestore()
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setattr(utils.utils, "get_firestore_db", lambda: db)
    record = _dm_record()
    record.event_id = "ibe_" + "4" * 40
    record.claim_key = "claim-replacement-authority"
    record.binding_snapshot["binding_id"] = "snapshot-a"
    replacement_settings = replace(
        _settings(),
        tenant_id="linas",
        binding_id="replacement-b",
    )
    observed: list[tuple[str, str, str]] = []
    provider_calls = 0

    async def process(
        _event: dict[str, Any],
        settings: MetaMessagingSettings,
        **kwargs: Any,
    ) -> dict[str, Any]:
        nonlocal provider_calls
        observed.append((settings.binding_id, kwargs["tenant_id"], kwargs["binding_id"]))

        async def send() -> dict[str, Any]:
            nonlocal provider_calls
            provider_calls += 1
            return {"success": True, "provider": "meta", "message_id": "replacement-once"}

        result = await attempts.execute_guarded_meta_send(
            event_id=kwargs["inbound_event_id"],
            surface="facebook_dm",
            binding_id=kwargs["binding_id"],
            send=send,
        )
        return {
            "delivery": "no_text",
            "retryable": False,
            "terminal": True,
            "duplicate": bool(result.get("duplicate_suppressed")),
        }

    async def settle(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(handler, "get_inbound_event", lambda _event_id: record)
    monkeypatch.setattr(handler, "_settings_from_snapshot", lambda *_args: replacement_settings)
    monkeypatch.setattr(handler, "mark_inbound_state", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("services.social_messaging_processor.process_meta_social_event", process)
    monkeypatch.setattr("services.durable_event_claim.complete_event_claim", settle)
    job = QueueJob.new(
        queue="high_priority",
        job_type="meta_inbound_process",
        tenant_id="linas",
        payload={"event_id": record.event_id, "kind": "meta_dm"},
    )

    await handle_meta_inbound_process(job)
    await handle_meta_inbound_process(job)

    assert observed == [
        ("replacement-b", "linas", "snapshot-a"),
        ("replacement-b", "linas", "snapshot-a"),
    ]
    assert provider_calls == 1
    document_id = attempts._attempt_document_id(record.event_id, "primary_reply")
    assert ("meta_outbound_attempts", document_id) in build_shared_meta_claim_deletion_plan(
        db, {"snapshot-a"}
    ).shared_documents
    assert ("meta_outbound_attempts", document_id) not in build_shared_meta_claim_deletion_plan(
        db, {"replacement-b"}
    ).shared_documents


@pytest.mark.asyncio
async def test_legacy_queue_passes_record_tenant_and_synthetic_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import services.queues.meta_inbound_handler as handler

    record = _dm_record()
    record.tenant_id = ""
    record.binding_snapshot = {"binding_id": "legacy-single-app", "tenant_id": "linas"}
    record.settings_snapshot = {"binding_id": "legacy-single-app"}
    observed: list[dict[str, Any]] = []

    async def process(*_args: Any, **kwargs: Any) -> dict[str, Any]:
        observed.append(kwargs)
        return {"delivery": "no_text", "retryable": False, "terminal": True}

    async def settle(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(handler, "get_inbound_event", lambda _event_id: record)
    monkeypatch.setattr(handler, "_settings_from_snapshot", lambda *_args: _settings())
    monkeypatch.setattr(handler, "mark_inbound_state", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("services.social_messaging_processor.process_meta_social_event", process)
    monkeypatch.setattr("services.durable_event_claim.complete_event_claim", settle)
    job = QueueJob.new(
        queue="high_priority",
        job_type="meta_inbound_process",
        tenant_id="linas",
        payload={"event_id": record.event_id, "kind": "meta_dm"},
    )

    await handle_meta_inbound_process(job)

    assert observed == [
        {
            "inbound_event_id": record.event_id,
            "tenant_id": "linas",
            "binding_id": "legacy-single-app",
            "simulation": False,
        }
    ]


@pytest.mark.asyncio
async def test_retryable_comment_result_releases_claim_and_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    import services.queues.meta_inbound_handler as handler

    states: list[dict[str, Any]] = []
    completed: list[str] = []
    released: list[str] = []

    async def process(_resolved: Any, **_kwargs: Any) -> CommentReplyResult:
        return CommentReplyResult(status="failed", reason="http_500")

    async def complete(_namespace: str, key: str, **_kwargs: Any) -> None:
        completed.append(key)

    async def release(_namespace: str, key: str, **_kwargs: Any) -> None:
        released.append(key)

    monkeypatch.setattr(handler, "get_inbound_event", lambda _event_id: _record())
    monkeypatch.setattr(handler, "_settings_from_snapshot", lambda *_args: _settings())
    monkeypatch.setattr(
        handler, "mark_inbound_state", lambda event_id, **kwargs: states.append({"event_id": event_id, **kwargs})
    )
    monkeypatch.setattr("services.meta_comment_replies.process_meta_comment_event", process)
    monkeypatch.setattr("services.durable_event_claim.complete_event_claim", complete)
    monkeypatch.setattr("services.durable_event_claim.release_event_claim", release)

    job = QueueJob.new(
        queue="high_priority",
        job_type="meta_inbound_process",
        tenant_id="linas",
        payload={"event_id": "event-comment-1", "kind": "meta_comment"},
    )
    with pytest.raises(RuntimeError, match="retryable Meta comment outcome"):
        await handle_meta_inbound_process(job)

    assert completed == []
    assert released == ["claim-comment-1"]
    assert any(item.get("state") == "failed" for item in states)
    assert not any(item.get("state") == "completed" for item in states)


@pytest.mark.asyncio
async def test_retryable_dm_result_releases_claim_and_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    import services.queues.meta_inbound_handler as handler

    states: list[dict[str, Any]] = []
    released: list[str] = []

    async def process(*_args: Any, **_kwargs: Any) -> dict[str, str]:
        return {"delivery": "delivery_pending", "logical_reply_id": "reply-1"}

    async def release(_namespace: str, key: str, **_kwargs: Any) -> None:
        released.append(key)

    monkeypatch.setattr(handler, "get_inbound_event", lambda _event_id: _dm_record())
    monkeypatch.setattr(handler, "_settings_from_snapshot", lambda *_args: _settings())
    monkeypatch.setattr(
        handler, "mark_inbound_state", lambda event_id, **kwargs: states.append({"event_id": event_id, **kwargs})
    )
    monkeypatch.setattr("services.social_messaging_processor.process_meta_social_event", process)
    monkeypatch.setattr("services.durable_event_claim.release_event_claim", release)

    job = QueueJob.new(
        queue="high_priority",
        job_type="meta_inbound_process",
        tenant_id="linas",
        payload={"event_id": "event-dm-1", "kind": "meta_dm"},
    )
    with pytest.raises(RuntimeError, match="retryable Meta DM outcome"):
        await handle_meta_inbound_process(job)

    assert released == ["claim-dm-1"]
    assert any(item.get("state") == "failed" for item in states)
    assert not any(item.get("state") == "completed" for item in states)


@pytest.mark.asyncio
async def test_unexpected_dm_failure_releases_claim_without_persisting_raw_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import services.queues.meta_inbound_handler as handler

    states: list[dict[str, Any]] = []
    released: list[str] = []

    async def process(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("provider-private-request-detail")

    async def release(_namespace: str, key: str, **_kwargs: Any) -> None:
        released.append(key)

    monkeypatch.setattr(handler, "get_inbound_event", lambda _event_id: _dm_record())
    monkeypatch.setattr(handler, "_settings_from_snapshot", lambda *_args: _settings())
    monkeypatch.setattr(
        handler,
        "mark_inbound_state",
        lambda event_id, **kwargs: states.append({"event_id": event_id, **kwargs}),
    )
    monkeypatch.setattr("services.social_messaging_processor.process_meta_social_event", process)
    monkeypatch.setattr("services.durable_event_claim.release_event_claim", release)

    job = QueueJob.new(
        queue="high_priority",
        job_type="meta_inbound_process",
        tenant_id="linas",
        payload={"event_id": "event-dm-1", "kind": "meta_dm"},
    )
    with pytest.raises(RuntimeError, match="provider-private-request-detail"):
        await handle_meta_inbound_process(job)

    assert released == ["claim-dm-1"]
    failed = [item for item in states if item.get("state") == "failed"][-1]
    assert failed["last_error"] == "exception:RuntimeError"
    assert "private-request-detail" not in repr(failed)


@pytest.mark.asyncio
@pytest.mark.parametrize("delivery", ("blocked_quota", "no_text", "permanent_block"))
async def test_terminal_dm_outcome_completes_without_retry(
    monkeypatch: pytest.MonkeyPatch,
    delivery: str,
) -> None:
    import services.queues.meta_inbound_handler as handler

    states: list[dict[str, Any]] = []
    completed: list[str] = []
    released: list[str] = []

    async def process(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"delivery": delivery, "retryable": False, "terminal": True}

    async def complete(_namespace: str, key: str, **_kwargs: Any) -> None:
        completed.append(key)

    async def release(_namespace: str, key: str, **_kwargs: Any) -> None:
        released.append(key)

    monkeypatch.setattr(handler, "get_inbound_event", lambda _event_id: _dm_record())
    monkeypatch.setattr(handler, "_settings_from_snapshot", lambda *_args: _settings())
    monkeypatch.setattr(
        handler,
        "mark_inbound_state",
        lambda event_id, **kwargs: states.append({"event_id": event_id, **kwargs}),
    )
    monkeypatch.setattr("services.social_messaging_processor.process_meta_social_event", process)
    monkeypatch.setattr("services.durable_event_claim.complete_event_claim", complete)
    monkeypatch.setattr("services.durable_event_claim.release_event_claim", release)

    job = QueueJob.new(
        queue="high_priority",
        job_type="meta_inbound_process",
        tenant_id="linas",
        payload={"event_id": "event-dm-1", "kind": "meta_dm"},
    )
    result = await handle_meta_inbound_process(job)

    assert result["ok"] is True
    assert completed == ["claim-dm-1"]
    assert released == []
    assert any(item.get("state") == "completed" and item.get("outbound_status") == delivery for item in states)


@pytest.mark.asyncio
async def test_sent_comment_result_completes_claim_once(monkeypatch: pytest.MonkeyPatch) -> None:
    import services.queues.meta_inbound_handler as handler

    states: list[dict[str, Any]] = []
    completed: list[str] = []

    async def process(_resolved: Any, **_kwargs: Any) -> CommentReplyResult:
        return CommentReplyResult(status="sent", reply_id="reply-1")

    async def complete(_namespace: str, key: str, **_kwargs: Any) -> None:
        completed.append(key)

    monkeypatch.setattr(handler, "get_inbound_event", lambda _event_id: _record())
    monkeypatch.setattr(handler, "_settings_from_snapshot", lambda *_args: _settings())
    monkeypatch.setattr(
        handler, "mark_inbound_state", lambda event_id, **kwargs: states.append({"event_id": event_id, **kwargs})
    )
    monkeypatch.setattr("services.meta_comment_replies.process_meta_comment_event", process)
    monkeypatch.setattr("services.durable_event_claim.complete_event_claim", complete)

    job = QueueJob.new(
        queue="high_priority",
        job_type="meta_inbound_process",
        tenant_id="linas",
        payload={"event_id": "event-comment-1", "kind": "meta_comment"},
    )
    result = await handle_meta_inbound_process(job)

    assert result["ok"] is True
    assert completed == ["claim-comment-1"]
    assert sum(item.get("state") == "completed" for item in states) == 1
