"""WAVE X10: CM-only inbound; booking OpenAI schemas gone; schedule museum gone."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_wave_x10_handlers_do_not_import_social_contact_routing() -> None:
    hits: list[str] = []
    for path in (ROOT / "handlers").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "social_contact_routing import" in text or "route_social_contact_request" in text:
            hits.append(str(path.relative_to(ROOT)))
    assert hits == []
    message = (ROOT / "handlers/text_handlers_message.py").read_text(encoding="utf-8")
    assert "social_contact_routing_detect import is_social_channel" in message


def test_wave_x10_booking_tools_and_schedule_gone() -> None:
    gone = (
        "utils/utils_tools_booking.py",
        "utils/utils_tools_lookup.py",
        "services/schedule_service.py",
    )
    leftover = [rel for rel in gone if (ROOT / rel).exists()]
    assert not leftover, leftover
    from utils.utils_tools import get_openai_tools_schema

    names = {str((t.get("function") or {}).get("name") or "") for t in get_openai_tools_schema()}
    assert names == set()
    tools = (ROOT / "services/owner_copilot/tools.py").read_text(encoding="utf-8")
    assert "tool_read_scheduled_posts" not in tools
    assert "read_scheduled_posts" not in (ROOT / "services/owner_copilot/tools_read.py").read_text(encoding="utf-8")
    queues = (ROOT / "services/queues/handlers.py").read_text(encoding="utf-8")
    assert "schedule_service" not in queues
    keep = (ROOT / "docs/KEEP_SURFACE.md").read_text(encoding="utf-8")
    assert "WAVE X10" in keep
    assert (ROOT / "services/integrations/social/social_contact_routing_detect.py").is_file()
    sfu = (ROOT / "services/smart_followup/social_schedule.py").read_text(encoding="utf-8")
    assert "is_social_channel" in sfu
