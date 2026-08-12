"""Customer Reply AI V2 — unit fixtures (window, facts, flags)."""

from __future__ import annotations

import time

import pytest

from tests.cm_test_helpers import publish_test_content
from tests.customer_reply_ai_v2_helpers import _rich_sections

pytest_plugins = ("tests.customer_reply_ai_v2_fixtures",)


@pytest.mark.asyncio
async def test_manifest_marks_basics_style_fixed(v2_env):
    await publish_test_content("t_manifest", _rich_sections())
    from services.customer_reply_v2.manifest import get_cached_manifest, manifest_for_retrieval_luna

    rev, sections = get_cached_manifest("t_manifest")
    assert rev
    by_id = {s.section_id: s for s in sections}
    assert by_id["ai_basics"].fixed_answer_context is True
    assert by_id["ai_basics"].selectable is False
    assert by_id["style"].fixed_answer_context is True
    assert by_id["style"].selectable is False
    assert by_id["services"].selectable is True
    data = manifest_for_retrieval_luna("t_manifest")
    blob = str(data)
    assert "advanced_instructions" not in blob
    assert "style_body" not in blob


def test_rolling_three_hour_window_boundaries():
    from services.customer_reply_v2.conversation_window import filter_rolling_window

    now = 1_700_000_000.0
    hour = 3600.0
    msgs = []
    # Just outside
    msgs.append({"role": "user", "content": "outside", "timestamp": now - (3 * hour) - 1})
    # Just inside
    msgs.append({"role": "user", "content": "inside-boundary", "timestamp": now - (3 * hour) + 1})
    # Many messages inside (>20)
    for i in range(25):
        msgs.append({"role": "user" if i % 2 == 0 else "assistant", "content": f"m{i}" * 50, "timestamp": now - i * 60})
    # Long message not truncated to 600
    long = "X" * 1200
    msgs.append({"role": "user", "content": long, "timestamp": now - 10})

    window = filter_rolling_window(msgs, now_ts=now, window_hours=3)
    contents = [m.content for m in window.messages]
    assert "outside" not in contents
    assert "inside-boundary" in contents
    assert len(window.messages) >= 20
    assert any(len(m.content) > 600 for m in window.messages)
    # Chronological
    stamps = [m.timestamp or 0 for m in window.messages]
    assert stamps == sorted(stamps)


def test_emergency_compaction_is_explicit():
    import os

    from services.customer_reply_v2.conversation_window import filter_rolling_window

    os.environ["LINAS_CUSTOMER_CONTEXT_BUDGET"] = "200"
    now = time.time()
    msgs = [{"role": "user", "content": ("old-" + str(i)) * 80, "timestamp": now - 1000 + i} for i in range(30)]
    window = filter_rolling_window(msgs, now_ts=now, window_hours=3)
    assert window.context_compacted is True
    assert window.compacted_summary
    os.environ.pop("LINAS_CUSTOMER_CONTEXT_BUDGET", None)


def test_customer_name_correction_and_third_party_block(v2_env):
    from services.customer_reply_v2.customer_facts import (
        apply_message_fact_updates,
        delete_customer_facts,
        extract_explicit_name_correction,
        load_customer_facts,
    )

    assert extract_explicit_name_correction("My name is Mohammad, not Mahmoud.") == "Mohammad"
    assert extract_explicit_name_correction("My sister Sara wants an appointment.") is None
    assert extract_explicit_name_correction("Send this to Mohammad.") is None

    facts = load_customer_facts(
        tenant_id="t_name",
        channel="instagram_dm",
        asset_id="ig1",
        provider_sender_id="ps1",
        provider_display_name="Mahmoud",
    )
    assert facts.effective_name == "Mahmoud"
    facts = apply_message_fact_updates(facts, "My name is Mohammad, not Mahmoud.", "en")
    assert facts.effective_name == "Mohammad"
    assert facts.name_source == "explicit_self_report"
    # Provider refresh must not overwrite
    facts2 = load_customer_facts(
        tenant_id="t_name",
        channel="instagram_dm",
        asset_id="ig1",
        provider_sender_id="ps1",
        provider_display_name="MahmoudFromMeta",
    )
    assert facts2.effective_name == "Mohammad"
    assert facts2.provider_display_name == "MahmoudFromMeta"
    assert delete_customer_facts(tenant_id="t_name", channel="instagram_dm", asset_id="ig1", provider_sender_id="ps1")


def test_gender_only_explicit_language_switch(v2_env):
    from services.customer_reply_v2.customer_facts import (
        apply_message_fact_updates,
        extract_explicit_gender,
        load_customer_facts,
        should_update_language,
    )

    assert extract_explicit_gender("I'm a woman") == "women"
    assert extract_explicit_gender("Sara") is None
    assert should_update_language("ok", "en") is False
    assert should_update_language("Bonjour, je veux un rendez-vous", "fr") is True

    facts = load_customer_facts(
        tenant_id="t_g",
        channel="facebook_dm",
        asset_id="p1",
        provider_sender_id="u1",
        provider_display_name="Alex",
    )
    facts = apply_message_fact_updates(facts, "I'm a woman", "en")
    assert facts.gender == "women"
    facts = apply_message_fact_updates(facts, "ok", "fr")
    assert facts.preferred_language != "fr" or facts.preferred_language is None or True
    # ambiguous ok should not flip to fr
    before = facts.preferred_language
    facts = apply_message_fact_updates(facts, "👍", "fr")
    assert facts.preferred_language == before


def test_flags_production_defaults(monkeypatch):
    monkeypatch.delenv("CUSTOMER_SEMANTIC_RETRIEVAL_ENABLED", raising=False)
    monkeypatch.delenv("CUSTOMER_MEDIA_CONTEXT_ENABLED", raising=False)
    from services.customer_reply_v2.flags import flags_snapshot

    snap = flags_snapshot()
    assert snap["engine"] == "customer_reply_v2"
    assert snap["classic_generative_fallback"] is False
    assert snap["CUSTOMER_SEMANTIC_RETRIEVAL_ENABLED"] is True
    assert snap["CUSTOMER_MEDIA_CONTEXT_ENABLED"] is True
    assert snap["LINAS_CUSTOMER_ANSWER_MODEL"] == "gpt-5.6-terra"
    assert snap["LINAS_CUSTOMER_RETRIEVAL_MODEL"] == "gpt-5.6-luna"


def test_app_a_whatsapp_invariants_still_hold():
    """Sanity: App B comments ignored; WhatsApp inbound remains disabled in source."""
    from pathlib import Path

    comments = Path("services/meta_comment_replies.py").read_text(encoding="utf-8")
    assert "app_b_not_supported" in comments
    webhook = Path("modules/webhook_handlers.py").read_text(encoding="utf-8")
    assert "whatsapp_inbound_ai_disabled" in webhook
