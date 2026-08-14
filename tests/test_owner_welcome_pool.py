"""Hardcoded welcome pool: size, banned status copy, picker, no LLM seed."""

from __future__ import annotations

from pathlib import Path

from services.welcome_pool import (
    BANNED_SNIPPETS,
    MIN_POOL_SIZE,
    POOLS,
    format_welcome,
    lines_for,
    pick_welcome,
    pick_welcome_line,
    reset_last_picks,
)


class _AlwaysZero:
    def randrange(self, n: int) -> int:
        del n
        return 0


def test_pool_size_per_locale() -> None:
    for lang in ("en", "ar", "fr"):
        pool = lines_for(lang)
        assert len(pool) >= MIN_POOL_SIZE
        assert len(set(pool)) == len(pool)
        assert all("{hi}" in line for line in pool)


def test_pool_has_no_banned_system_status_phrases() -> None:
    for lang, pool in POOLS.items():
        blob = "\n".join(pool).lower()
        for snippet in BANNED_SNIPPETS:
            assert snippet.lower() not in blob, f"{lang}: banned {snippet!r}"
        for extra in ("ai setup", "system copilot", "core looks configured"):
            assert extra not in blob


def test_picker_returns_pool_member_and_skips_last() -> None:
    reset_last_picks()
    rng = _AlwaysZero()
    first = pick_welcome_line(language="en", user_key="u-test", rng=rng)
    second = pick_welcome_line(language="en", user_key="u-test", rng=rng)
    pool = lines_for("en")
    assert first == pool[0]
    assert second == pool[1]
    assert first != second


def test_pick_welcome_interpolates_display_name() -> None:
    reset_last_picks()
    text = pick_welcome(language="en", user_key="named", hi="Hello mahmoud", rng=_AlwaysZero())
    assert text.startswith("Hello mahmoud")
    assert text == format_welcome(lines_for("en")[0], hi="Hello mahmoud")


def test_build_greeting_uses_pool_not_llm(monkeypatch) -> None:
    from services.owner_ai_greeting import build_greeting

    monkeypatch.setattr(
        "services.owner_ai_greeting.read_owner_profile",
        lambda _uid: {
            "display_name": "mahmoud",
            "gender": "unset",
            "preferred_language": "en",
            "form_of_address": None,
            "address_prompt_asked": True,
        },
    )
    monkeypatch.setattr("services.owner_ai_greeting.resolve_setup_stage", lambda _tid: "fully_configured")
    reset_last_picks()
    g = build_greeting(tenant_id="t1", user_id="u-pool", language="en")
    pool_texts = {format_welcome(line, hi="Hello mahmoud") for line in lines_for("en")}
    assert g["text"] in pool_texts
    assert "core looks configured" not in g["text"].lower()
    assert "ai setup" not in g["text"].lower()
    greeting_src = Path("services/owner_ai_greeting.py").read_text(encoding="utf-8")
    assert "pick_welcome" in greeting_src
    assert "openai" not in greeting_src.lower()
    assert "generate" not in greeting_src.lower()
    api_src = Path("modules/owner_ai_api.py").read_text(encoding="utf-8")
    assert "build_greeting" in api_src
    assert "chat.completions" not in api_src


def test_guest_greeting_uses_same_pool() -> None:
    from services.guest_ai_service import build_guest_greeting

    reset_last_picks()
    text = build_guest_greeting(language="fr", session_id="sess-1")
    pool_texts = {format_welcome(line, hi="Bonjour") for line in lines_for("fr")}
    assert text in pool_texts
    assert "configuration ia" not in text.lower()
