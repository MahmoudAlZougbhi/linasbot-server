"""Wave 4 reliability: durable claims, queue persistence, preview gate, templates."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

from services.durable_event_claim import (
    complete_event_claim,
    release_event_claim,
    release_job_lock,
    try_acquire_job_lock,
    try_claim_event,
)


class TestDurableClaims:
    def test_file_claim_exclusive_and_release(self):
        async def _run():
            with patch("services.durable_event_claim.get_firestore_db", create=True):
                with patch("utils.utils.get_firestore_db", return_value=None):
                    a = await try_claim_event("unit_ns", "mid-1", ttl_seconds=60)
                    b = await try_claim_event("unit_ns", "mid-1", ttl_seconds=60)
                    assert a is True
                    assert b is False
                    await release_event_claim("unit_ns", "mid-1")
                    c = await try_claim_event("unit_ns", "mid-1", ttl_seconds=60)
                    assert c is True
                    await complete_event_claim("unit_ns", "mid-1")
                    d = await try_claim_event("unit_ns", "mid-1", ttl_seconds=60)
                    assert d is False

        asyncio.run(_run())

    def test_scheduler_job_lock(self):
        assert try_acquire_job_lock("job_a", ttl_seconds=30) is True
        assert try_acquire_job_lock("job_a", ttl_seconds=30) is False
        release_job_lock("job_a")
        assert try_acquire_job_lock("job_a", ttl_seconds=30) is True
        release_job_lock("job_a")


class TestReadyEndpoint:
    def test_ready_is_public(self):
        # Create a loop before importing modules that construct asyncio.Lock at import time.
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            from fastapi.testclient import TestClient

            import modules.dashboard_api  # noqa: F401
            from modules.api_security import is_public_api
            from modules.core import app

            assert is_public_api("GET", "/api/ready")
            client = TestClient(app)
            r = client.get("/api/ready")
            assert r.status_code in {200, 503}
            body = r.json()
            assert body.get("role") == "readiness"
            assert "checks" in body
            assert "openai_api_key" in body["checks"]
        finally:
            try:
                loop.close()
            except Exception:
                pass
            # Leave a usable loop for later TestClient imports in the same pytest process.
            asyncio.set_event_loop(asyncio.new_event_loop())


class TestFlowLogPrivacy:
    def test_masks_phone_and_omits_full_prompts_by_default(self, monkeypatch, tmp_path):
        monkeypatch.delenv("FLOW_LOG_FULL_PROMPTS", raising=False)
        monkeypatch.setenv("INTERACTION_FLOW_DEBUG", "1")
        from services import interaction_flow_logger as ifl

        monkeypatch.setattr(ifl, "FLOW_LOG_FILE", str(tmp_path / "activity_flow.jsonl"))
        monkeypatch.setattr(ifl, "_FLOW_BUFFER", ifl.deque(maxlen=50))
        monkeypatch.setattr(ifl, "_INITIALIZED", False)
        ifl.log_interaction(
            user_id="96170123456",
            user_message="hello",
            bot_to_user="hi",
            source="gpt",
            user_phone="96170123456",
            ai_query_summary="FULL PROMPT " * 100,
            bot_sent_to_ai_full="SECRET PROMPT CONTENT",
        )
        entry = list(ifl._FLOW_BUFFER)[-1]
        assert entry.get("user_phone") is None
        assert "123456" not in (entry.get("user_id") or "")
        assert entry.get("bot_sent_to_ai_full") is None
        assert len(entry.get("ai_query_summary") or "") <= 500
