"""Armed soak jobs stop at the OpenAI gate and skip claim/model work."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from services.queues.meta_inbound_handler import handle_meta_inbound_process
from services.queues.models import QueueJob


@pytest.mark.asyncio
async def test_soak_gate_skips_get_mark_claim_and_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    import services.queues.meta_inbound_handler as handler

    marks: list[dict[str, Any]] = []
    bumps: list[str] = []

    monkeypatch.setattr(
        handler,
        "get_inbound_event",
        lambda *_args, **_kwargs: pytest.fail("soak job read Firestore inbound event"),
    )
    monkeypatch.setattr("services.scale.soak_arm.job_requests_soak_simulation", lambda _job: True)
    monkeypatch.setattr(
        "services.scale.inbound_event_store.mark_inbound_state",
        lambda *_args, **kwargs: marks.append(kwargs),
    )
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
            payload={"event_id": "event-soak-1", "kind": "meta_dm", "_linas_soak_simulation": True},
        )
    )

    assert result == {
        "ok": True,
        "kind": "meta_dm",
        "event_id": "event-soak-1",
        "openai_gate": True,
        "soak": True,
    }
    assert marks == []
    assert bumps == ["openai_ready"]


def test_soak_gate_is_inert_without_arm() -> None:
    from services.queues.meta_inbound_soak_gate import maybe_finish_soak_at_openai_gate

    assert maybe_finish_soak_at_openai_gate(soak=False, kind="meta_dm", event_id="e") is None
