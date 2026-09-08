"""Reconnect continuity, live binding re-resolve, and reconcile semantics."""

from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from services.meta_app_registry import APP_A_KEY, MetaAppRegistry, MetaBindingCredential
from services.meta_live_binding import resolve_live_outbound_binding
from services.queues.handlers import PermanentJobError
from services.scale.inbound_event_reconcile_live import action_if_ingress_job_already_owns
from services.scale.message_combine_schedule import schedule_combine_flush
from services.scale.message_combine_store import append_chunk, peek_pending, save_context, set_combine_redis_for_tests

IG_ID = "17841413184256533"
IG_SCOPES = (
    "instagram_business_basic",
    "instagram_business_manage_messages",
    "instagram_business_manage_comments",
)


@pytest.fixture
def registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> MetaAppRegistry:
    monkeypatch.setenv("META_MULTI_APP_REGISTRY_ENABLED", "true")
    monkeypatch.setenv("META_APP_A_ID", "2963733803971681")
    monkeypatch.setenv("META_APP_A_SECRET", "app-a-secret-tests")
    monkeypatch.setenv("META_APP_A_WEBHOOK_VERIFY_TOKEN", "verify-a")
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_APP_ID", "1035856539045307")
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_APP_SECRET", "instagram-app-secret-tests")
    monkeypatch.setenv("META_CREDENTIAL_ENCRYPTION_KEY", "ig-reconnect-secret-tests-1234567890ab")
    return MetaAppRegistry(
        store_path=tmp_path / "registry.json",
        audit_path=tmp_path / "audit.jsonl",
        master_secret="ig-reconnect-secret-tests-1234567890ab",
    )


def _authorize(registry: MetaAppRegistry, *, token: str, reconnect: bool = False) -> Any:
    binding = registry.authorize_oauth_asset(
        tenant_id="linas",
        channel="instagram",
        asset_id=IG_ID,
        page_id="",
        instagram_account_id=IG_ID,
        app_key=APP_A_KEY,
        credential=MetaBindingCredential(
            access_token=token,
            token_app_id="1035856539045307",
            token_profile_id=IG_ID,
            scopes=IG_SCOPES,
            expires_at=int(time.time()) + 30 * 24 * 3600,
            authorized_meta_user_id="112233",
            auth_flow="instagram_login",
        ),
        actor_id="owner",
        instagram_username="clinic_ig",
        status="testing" if reconnect else "active",
        auth_flow="instagram_login",
        webhook_subscription_status="ready",
        webhook_subscribed_fields=("comments", "messages", "messaging_postbacks"),
        create_new_binding=reconnect,
    )
    if not reconnect:
        return binding
    return registry.activate_staged_binding(
        binding.binding_id,
        actor_id="owner",
        expected_generation=binding.generation,
        replace_existing=True,
    )


def test_b_reconnect_supersedes_old_and_selects_new(registry: MetaAppRegistry, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("services.meta_app_registry.get_meta_app_registry", lambda: registry)
    old = _authorize(registry, token="old-token")
    new = _authorize(registry, token="new-token", reconnect=True)
    refreshed_old = next(
        item for item in registry.list_bindings(include_inactive=True) if item.binding_id == old.binding_id
    )
    refreshed_new = next(
        item for item in registry.list_bindings(include_inactive=True) if item.binding_id == new.binding_id
    )
    assert refreshed_new.active is True
    assert refreshed_old.active is False
    assert refreshed_old.status in {"disconnected", "superseded", "inactive"}
    live = resolve_live_outbound_binding(
        {"tenant_id": "linas", "channel": "instagram", "auth_flow": "instagram_login"},
        {
            "binding_id": old.binding_id,
            "tenant_id": "linas",
            "channel": "instagram",
            "asset_id": IG_ID,
            "app_key": APP_A_KEY,
            "auth_flow": "instagram_login",
        },
    )
    assert live.binding_id == new.binding_id
    assert registry.get_credential(live).access_token == "new-token"


def test_c_pending_combine_reresolves_active_instagram(
    registry: MetaAppRegistry, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("services.meta_app_registry.get_meta_app_registry", lambda: registry)
    old = _authorize(registry, token="old-token")
    new = _authorize(registry, token="new-token", reconnect=True)
    live = resolve_live_outbound_binding(
        {"tenant_id": "linas"},
        {
            "binding_id": old.binding_id,
            "tenant_id": "linas",
            "channel": "instagram",
            "asset_id": IG_ID,
            "app_key": APP_A_KEY,
            "auth_flow": "instagram_login",
        },
    )
    assert live.binding_id == new.binding_id
    assert live.auth_flow == "instagram_login"
    assert registry.get_credential(live).access_token != "old-token"


def test_d_reconcile_does_not_complete_combine_scheduled(monkeypatch: pytest.MonkeyPatch) -> None:
    rec = SimpleNamespace(
        event_id="ibe_" + "b" * 40,
        kind="meta_dm",
        tenant_id="linas",
        outbound_status="combine_scheduled",
    )
    marks: list[dict[str, object]] = []
    monkeypatch.setattr(
        "services.scale.inbound_event_reconcile_live.lookup_ingress_job",
        lambda _rec: SimpleNamespace(id="job-ingress", status="completed"),
    )
    monkeypatch.setattr(
        "services.scale.inbound_event_reconcile_live.mark_inbound_state",
        lambda *_args, **kwargs: marks.append(kwargs),
    )
    result = action_if_ingress_job_already_owns(rec)  # type: ignore[arg-type]
    assert result is not None
    assert result["action"] == "await_combine_or_delivery"
    assert marks == []


def test_e_reconcile_catchup_only_when_outbound_was_sent(monkeypatch: pytest.MonkeyPatch) -> None:
    rec = SimpleNamespace(
        event_id="ibe_" + "c" * 40,
        kind="meta_dm",
        tenant_id="linas",
        outbound_status="delivered",
    )
    marks: list[dict[str, object]] = []
    monkeypatch.setattr(
        "services.scale.inbound_event_reconcile_live.lookup_ingress_job",
        lambda _rec: SimpleNamespace(id="job-done", status="completed"),
    )
    monkeypatch.setattr(
        "services.scale.inbound_event_reconcile_live.mark_inbound_state",
        lambda *_args, **kwargs: marks.append(kwargs),
    )
    result = action_if_ingress_job_already_owns(rec)  # type: ignore[arg-type]
    assert result is not None
    assert result["action"] == "ledger_catchup_completed"
    assert marks[0]["state"] == "completed"


def test_j_superseded_instagram_credential_never_selected(
    registry: MetaAppRegistry, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("services.meta_app_registry.get_meta_app_registry", lambda: registry)
    old = _authorize(registry, token="old-token")
    _authorize(registry, token="new-token", reconnect=True)
    with pytest.raises(PermanentJobError):
        resolve_live_outbound_binding(
            {"tenant_id": "linas", "channel": "instagram"},
            {
                "binding_id": old.binding_id,
                "tenant_id": "other-tenant",
                "channel": "instagram",
                "asset_id": IG_ID,
                "app_key": APP_A_KEY,
                "auth_flow": "instagram_login",
            },
        )
    live = resolve_live_outbound_binding(
        {"tenant_id": "linas", "channel": "instagram"},
        {
            "binding_id": old.binding_id,
            "tenant_id": "linas",
            "channel": "instagram",
            "asset_id": IG_ID,
            "app_key": APP_A_KEY,
            "auth_flow": "instagram_login",
        },
    )
    assert registry.get_credential(live).access_token == "new-token"


def test_combine_processing_job_enqueues_follow_up(monkeypatch: pytest.MonkeyPatch) -> None:
    stored: list[Any] = []

    class _Job:
        def __init__(self, *, status: str, job_id: str) -> None:
            self.status = status
            self.id = job_id

    class _Backend:
        def get_by_idempotency(self, _queue: str, _tenant: str, key: str) -> Any:
            if key == "combine_flush:user-1":
                return _Job(status="processing", job_id="running")
            return None

        def clear_idempotency(self, *_args: Any, **_kwargs: Any) -> None:
            return None

        def set_available_at(self, *_args: Any, **_kwargs: Any) -> None:
            raise AssertionError("must not bump a processing combine job")

        def enqueue(self, job: Any) -> Any:
            stored.append(job)
            job.id = "follow-up"
            return job

    monkeypatch.setattr(
        "services.job_queue.job_queue",
        SimpleNamespace(_redis=_Backend()),
        raising=False,
    )
    monkeypatch.setattr("services.omnichannel.queues.physical_queue_for", lambda _logical: "high_priority")
    job_id = schedule_combine_flush(
        user_key="user-1",
        tenant_id="linas",
        conversation_key="linas:instagram:user-1",
        due_at=time.time() + 3,
        payload={"generation": 7, "channel": "instagram"},
    )
    assert job_id == "follow-up"
    assert stored[0].payload["user_key"] == "user-1"
    assert stored[0].idempotency_key == "combine_flush:user-1:g7"


def test_combine_flush_reschedules_stranded_chunks(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Redis:
        def __init__(self) -> None:
            self.data: dict[str, Any] = {}

        def sadd(self, key: str, value: str) -> int:
            bucket = self.data.setdefault(key, set())
            before = len(bucket)
            bucket.add(value)
            return 0 if len(bucket) == before else 1

        def expire(self, *_args: Any, **_kwargs: Any) -> None:
            return None

        def pipeline(self, *_args: Any, **_kwargs: Any) -> Any:
            return self

        def rpush(self, key: str, value: str) -> None:
            self.data.setdefault(key, []).append(value)

        def incr(self, key: str) -> int:
            self.data[key] = int(self.data.get(key) or 0) + 1
            return self.data[key]

        def set(self, key: str, value: str, ex: int | None = None) -> None:
            self.data[key] = value

        def get(self, key: str) -> Any:
            return self.data.get(key)

        def lrange(self, key: str, _start: int, _end: int) -> list[Any]:
            return list(self.data.get(key) or [])

        def delete(self, key: str) -> None:
            self.data.pop(key, None)

        def execute(self) -> list[Any]:
            return [1, True, 1, True, True]

    client = _Redis()
    set_combine_redis_for_tests(client)
    try:
        append_chunk("user-1", text="hi", event_id="ibe_1", delay_seconds=0)
        save_context("user-1", {"tenant_id": "linas", "channel": "instagram", "binding_id": "old"})
        assert peek_pending("user-1")
        scheduled: list[str] = []
        monkeypatch.setattr(
            "services.scale.message_combine_schedule.schedule_combine_flush",
            lambda **kwargs: scheduled.append(str(kwargs["user_key"])) or "job-2",
        )
        from services.queues.combine_flush_handler import _reschedule_if_pending
        from services.queues.models import QueueJob

        job = QueueJob.new(
            queue="high_priority", job_type="combine_flush", tenant_id="linas", payload={"user_key": "user-1"}
        )
        _reschedule_if_pending("user-1", job, {"tenant_id": "linas", "channel": "instagram"})
        assert scheduled == ["user-1"]
    finally:
        set_combine_redis_for_tests(None)


@pytest.mark.asyncio
async def test_inline_combine_scheduled_stays_queued(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.scale.meta_webhook_accept import process_inline_meta_dm

    states: list[str] = []

    async def run_under(_handle: Any, ttl_seconds: float, operation: Any) -> Any:
        del _handle, ttl_seconds
        return await operation()

    async def process(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"delivery": "combine_scheduled", "retryable": False, "deferred": True}

    async def complete(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr("services.durable_event_claim.run_under_event_claim", run_under)
    monkeypatch.setattr("services.durable_event_claim.complete_event_claim", complete)
    monkeypatch.setattr("services.scale.meta_ingress.mark_dm_processing", lambda *_a, **_k: None)
    monkeypatch.setattr(
        "services.scale.inbound_event_store.mark_inbound_state",
        lambda _event_id, **kwargs: states.append(str(kwargs.get("state"))),
    )
    monkeypatch.setattr(
        "services.scale.meta_ingress.mark_dm_completed",
        lambda *_a, **_k: states.append("completed"),
    )
    resolved = SimpleNamespace(
        event={"channel": "instagram"},
        settings=SimpleNamespace(app_key=APP_A_KEY),
        binding=SimpleNamespace(binding_id="5a7bf681dead", channel="instagram", tenant_id="linas"),
    )
    await process_inline_meta_dm(
        resolved,  # type: ignore[arg-type]
        event_id="ibe_inline",
        global_key="instagram:ig:mid",
        claim_handle=SimpleNamespace(),
        process_dm=process,
    )
    assert "queued" in states
    assert "completed" not in states
