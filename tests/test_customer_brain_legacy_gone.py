"""Customer Brain dead islands and legacy reply engines stay gone."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

GONE_PATHS = (
    "services/brain/openai_usage_service.py",
    "services/brain/ingest/multimodal.py",
    "services/brain/inbound/message_buffer.py",
    "services/brain/readiness.py",
    "services/brain/relations/graph.py",
    "services/brain/safety_gateway.py",
    "services/brain/search/index_backfill.py",
    "services/brain/inbound/photo_handlers.py",
    "services/brain/brain_off.py",
    "services/brain/search/versioning.py",
    "services/brain/precedence.py",
    "services/brain/usage.py",
    "services/brain/ingest/__init__.py",
    "services/brain/relations/__init__.py",
    "services/brain/retrieve/expand.py",
    "services/brain/greeting.py",
    "services/brain/conversation_router.py",
    "services/brain/templates.py",
    "services/brain/inbound/text_handlers_message_greeting.py",
)

KEEP_PATHS = (
    "services/brain/retrieve/hydrate.py",
    "services/brain/retrieve/query_expand.py",
    "services/brain/greeting_detect.py",
    "services/brain/greeting_eligibility.py",
    "services/brain/human_request.py",
    "services/brain/owner_protocol.py",
    "services/brain/agent/greeting_turn.py",
    "services/brain/conversation_router_patterns.py",
)


def test_dead_and_legacy_brain_paths_are_gone() -> None:
    for rel in GONE_PATHS:
        assert not (ROOT / rel).exists(), rel


def test_modern_brain_owners_remain() -> None:
    for rel in KEEP_PATHS:
        assert (ROOT / rel).is_file(), rel


def test_brain_source_has_no_canned_greeting_or_template_engines() -> None:
    blob = "\n".join(path.read_text(encoding="utf-8") for path in (ROOT / "services/brain").rglob("*.py"))
    assert "GREETING_TEMPLATES" not in blob
    assert "def safe_greeting_text" not in blob
    assert "def brain_template" not in blob
    assert "from services.brain.templates" not in blob
    assert "from services.brain.greeting import" not in blob
    assert "from services.brain.retrieve.expand" not in blob
