"""LOC split: MAHMOUD_MOBILE_PROMPT screen sections under 500 lines."""

from __future__ import annotations

from pathlib import Path


def _line_count(rel: str) -> int:
    return len(Path(rel).read_text(encoding="utf-8").splitlines())


PARTS = [
    "docs/design/MAHMOUD_MOBILE_PROMPT.md",
    "docs/design/MAHMOUD_MOBILE_PROMPT_spec_and_visual.md",
    "docs/design/MAHMOUD_MOBILE_PROMPT_guest_chat.md",
    "docs/design/MAHMOUD_MOBILE_PROMPT_owner_proposal.md",
    "docs/design/MAHMOUD_MOBILE_PROMPT_drawer.md",
    "docs/design/MAHMOUD_MOBILE_PROMPT_content_management.md",
    "docs/design/MAHMOUD_MOBILE_PROMPT_setup_and_meta.md",
    "docs/design/MAHMOUD_MOBILE_PROMPT_live_chat.md",
    "docs/design/MAHMOUD_MOBILE_PROMPT_settings.md",
    "docs/design/MAHMOUD_MOBILE_PROMPT_quality_and_verification.md",
]


def test_mahmoud_mobile_prompt_parts_under_500_lines() -> None:
    for rel in PARTS:
        assert _line_count(rel) < 500, rel


def test_mahmoud_mobile_prompt_index_links_screen_sections() -> None:
    index = Path("docs/design/MAHMOUD_MOBILE_PROMPT.md").read_text(encoding="utf-8")
    assert "MAHMOUD_MOBILE_PROMPT_guest_chat.md" in index
    assert "MAHMOUD_MOBILE_PROMPT_owner_proposal.md" in index
    assert "MAHMOUD_MOBILE_PROMPT_live_chat.md" in index
    assert "MAHMOUD_MOBILE_PROMPT_content_management.md" in index
    assert "MAHMOUD_MOBILE_PROMPT_settings.md" in index
    guest = Path("docs/design/MAHMOUD_MOBILE_PROMPT_guest_chat.md").read_text(encoding="utf-8")
    assert "Guest Chat" in guest
    live = Path("docs/design/MAHMOUD_MOBILE_PROMPT_live_chat.md").read_text(encoding="utf-8")
    assert "Live Chat" in live
