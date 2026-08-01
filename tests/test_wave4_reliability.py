"""Wave 4 reliability: durable claims, queue persistence, preview gate, templates."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

_TEST_ROOT = tempfile.mkdtemp(prefix="linas_wave4_")
os.environ["LINASBOT_DATA_ROOT"] = _TEST_ROOT
os.environ.setdefault("LINASLASER_API_BASE_URL", "https://example.com")
os.environ.setdefault("LINASLASER_API_TOKEN", "test-token")
os.environ.setdefault("DASHBOARD_AUTH_SECRET", "wave4-test-secret")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-a-real-key")


from services.durable_event_claim import (
    complete_event_claim,
    release_event_claim,
    release_job_lock,
    try_acquire_job_lock,
    try_claim_event,
)
from services.smart_messaging import SmartMessagingService, deliver_scheduled_smart_whatsapp


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


class TestSmartMessagingPersistence:
    def test_pending_queue_survives_reload(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LINASBOT_DATA_ROOT", str(tmp_path))
        # Re-import paths under new root
        from storage import persistent_storage as ps

        monkeypatch.setattr(ps, "_DATA_ROOT", tmp_path)
        monkeypatch.setattr(ps, "SMART_MESSAGING_DIR", tmp_path / "smart_messaging")
        monkeypatch.setattr(
            ps, "PENDING_SMART_MESSAGES_FILE", tmp_path / "smart_messaging" / "pending_smart_messages.json"
        )
        monkeypatch.setattr(ps, "SENT_SMART_MESSAGES_FILE", tmp_path / "smart_messaging" / "sent_smart_messages.json")
        monkeypatch.setattr(ps, "MESSAGE_TEMPLATES_FILE", tmp_path / "smart_messaging" / "message_templates.json")
        monkeypatch.setattr(ps, "APP_SETTINGS_FILE", tmp_path / "settings" / "app_settings.json")
        monkeypatch.setattr(
            ps, "SERVICE_TEMPLATE_MAPPING_FILE", tmp_path / "smart_messaging" / "service_template_mapping.json"
        )
        (tmp_path / "smart_messaging").mkdir(parents=True, exist_ok=True)
        (tmp_path / "settings").mkdir(parents=True, exist_ok=True)
        (tmp_path / "settings" / "app_settings.json").write_text(
            json.dumps({"smartMessaging": {"enabled": True, "previewBeforeSend": False}}),
            encoding="utf-8",
        )

        svc = SmartMessagingService()
        svc.SENT_MESSAGES_FILE = str(tmp_path / "smart_messaging" / "sent_smart_messages.json")
        svc.QUEUE_FILE = str(tmp_path / "smart_messaging" / "pending_smart_messages.json")
        svc.templates_file = str(tmp_path / "smart_messaging" / "message_templates.json")
        svc.settings_file = str(tmp_path / "settings" / "app_settings.json")
        svc.mapping_file = str(tmp_path / "smart_messaging" / "service_template_mapping.json")
        svc.scheduled_messages = {}
        svc.message_templates = {"reminder_24h": {"ar": "hi {name}", "en": "hi {name}"}}

        mid = svc.schedule_message(
            customer_phone="96170000000",
            message_type="reminder_24h",
            send_at=datetime.now() + timedelta(hours=1),
            placeholders={"name": "Test"},
            language="ar",
        )
        assert mid
        assert Path(svc.QUEUE_FILE).exists()
        data = json.loads(Path(svc.QUEUE_FILE).read_text(encoding="utf-8"))
        assert mid in data
        assert data[mid]["status"] == "scheduled"

        svc2 = SmartMessagingService()
        svc2.SENT_MESSAGES_FILE = svc.SENT_MESSAGES_FILE
        svc2.QUEUE_FILE = svc.QUEUE_FILE
        svc2.templates_file = svc.templates_file
        svc2.settings_file = svc.settings_file
        svc2.mapping_file = svc.mapping_file
        svc2.scheduled_messages = {}
        svc2._load_sent_messages()
        svc2._load_pending_queue()
        assert mid in svc2.scheduled_messages
        assert svc2.scheduled_messages[mid]["status"] == "scheduled"

    def test_preview_mode_forces_pending_approval(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LINASBOT_DATA_ROOT", str(tmp_path))
        (tmp_path / "smart_messaging").mkdir(parents=True, exist_ok=True)
        (tmp_path / "settings").mkdir(parents=True, exist_ok=True)
        (tmp_path / "settings" / "app_settings.json").write_text(
            json.dumps({"smartMessaging": {"enabled": True, "previewBeforeSend": True}}),
            encoding="utf-8",
        )
        svc = SmartMessagingService()
        svc.SENT_MESSAGES_FILE = str(tmp_path / "smart_messaging" / "sent_smart_messages.json")
        svc.QUEUE_FILE = str(tmp_path / "smart_messaging" / "pending_smart_messages.json")
        svc.settings_file = str(tmp_path / "settings" / "app_settings.json")
        svc.message_templates = {"reminder_24h": {"ar": "hi", "en": "hi"}}
        svc.scheduled_messages = {}

        with patch.object(svc, "_add_to_preview_queue") as add_preview:
            mid = svc.schedule_message(
                customer_phone="96170000001",
                message_type="reminder_24h",
                send_at=datetime.now() + timedelta(hours=1),
                placeholders={},
                language="ar",
                metadata={"source": "missed_paused_campaign"},
            )
            assert mid
            add_preview.assert_called_once_with(mid)


class TestTemplateRequired:
    def test_deliver_rejects_freeform_without_template(self):
        async def _run():
            adapter = MagicMock()
            adapter.send_text_message = MagicMock()
            with patch(
                "services.montymobile_template_service.montymobile_template_service.get_template_info",
                return_value=None,
            ):
                with patch(
                    "services.whatsapp_adapters.safe_send_adapter._should_dry_run",
                    return_value=False,
                ):
                    result = await deliver_scheduled_smart_whatsapp(
                        adapter,
                        phone="96170000002",
                        template_id="reminder_24h",
                        language="ar",
                        placeholders={},
                        rendered_text="hello",
                    )
            assert result.get("success") is False
            assert result.get("template_required") is True
            adapter.send_text_message.assert_not_called()

        asyncio.run(_run())


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
