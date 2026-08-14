"""Meta ingress must not enqueue when durable workers are not activated."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from services.scale.meta_ingress import _try_enqueue


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
