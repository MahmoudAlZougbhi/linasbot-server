"""Inbound handler treats combine deferral as queued, not a retry/DLQ."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

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


@pytest.mark.asyncio
async def test_combine_scheduled_keeps_event_queued(monkeypatch: pytest.MonkeyPatch) -> None:
    import services.queues.meta_inbound_handler as handler

    states: list[str] = []
    record = SimpleNamespace(
        event_id="event-dm-combine",
        kind="meta_dm",
        tenant_id="linas",
        state="accepted",
        claim_key="claim-dm-1",
        payload={"sender_id": "s1", "text": "hi", "channel": "facebook"},
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

    async def process(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"delivery": "combine_scheduled", "retryable": False, "deferred": True}

    async def settle(*_args: Any, **_kwargs: Any) -> None:
        return None

    def mark(_event_id: str, *, state: str, **_kwargs: Any) -> None:
        states.append(state)

    monkeypatch.setattr(handler, "get_inbound_event", lambda _event_id: record)
    monkeypatch.setattr(handler, "_settings_from_snapshot", lambda *_args: SimpleNamespace())
    monkeypatch.setattr(handler, "mark_inbound_state", mark)
    monkeypatch.setattr("services.social_messaging_processor.process_meta_social_event", process)
    monkeypatch.setattr("services.durable_event_claim.complete_event_claim", settle)

    job = QueueJob.new(
        queue="high_priority",
        job_type="meta_inbound_process",
        tenant_id="linas",
        payload={"event_id": record.event_id, "kind": "meta_dm"},
    )
    result = await handler.handle_meta_inbound_process(job)
    assert result["deferred"] is True
    assert "queued" in states
    assert "dead_letter" not in states
    assert "completed" not in states
