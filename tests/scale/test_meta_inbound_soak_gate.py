"""Armed soak jobs stop at the OpenAI gate and skip claim/model work."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from services.queues.meta_inbound_handler import handle_meta_inbound_process
from services.queues.models import QueueJob


@pytest.mark.asyncio
async def test_soak_gate_skips_claim_and_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    import services.queues.meta_inbound_handler as handler

    record = SimpleNamespace(
        event_id="event-soak-1",
        kind="meta_dm",
        tenant_id="linas",
        state="queued",
        claim_key="claim-soak-1",
        payload={"_linas_soak_simulation": True, "text": "hi"},
        settings_snapshot={},
        binding_snapshot={},
    )
    marks: list[dict[str, Any]] = []
    bumps: list[str] = []

    monkeypatch.setattr(handler, "get_inbound_event", lambda _event_id: record)
    monkeypatch.setattr("services.scale.soak_arm.job_requests_soak_simulation", lambda _job: True)

    def fake_mark(_event_id: str, **kwargs: Any) -> None:
        marks.append(kwargs)

    monkeypatch.setattr("services.scale.inbound_event_store.mark_inbound_state", fake_mark)
    monkeypatch.setattr("services.scale.rate_window.bump", lambda kind, n=1: bumps.append(str(kind)))
    monkeypatch.setattr(
        "services.durable_event_claim.try_claim_event_handle",
        lambda *_args, **_kwargs: pytest.fail("soak job claimed a Firestore lease"),
    )
    monkeypatch.setattr(
        "services.social_messaging_processor.process_meta_social_event",
        lambda *_args, **_kwargs: pytest.fail("soak job entered OpenAI"),
    )

    result = await handle_meta_inbound_process(
        QueueJob.new(
            queue="high_priority",
            job_type="meta_inbound_process",
            tenant_id="linas",
            payload={"event_id": record.event_id, "kind": "meta_dm", "_linas_soak_simulation": True},
        )
    )

    assert result == {
        "ok": True,
        "kind": "meta_dm",
        "event_id": record.event_id,
        "openai_gate": True,
        "soak": True,
    }
    assert marks == [
        {
            "state": "completed",
            "outbound_status": "openai_gate_reached",
            "last_error": "soak_pipeline_only",
        }
    ]
    assert bumps == ["openai_ready"]


def test_soak_gate_is_inert_without_arm() -> None:
    from services.queues.meta_inbound_soak_gate import maybe_finish_soak_at_openai_gate

    assert maybe_finish_soak_at_openai_gate(soak=False, rec=SimpleNamespace(kind="meta_dm"), event_id="e") is None
