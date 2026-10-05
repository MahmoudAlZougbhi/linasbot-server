"""Owner confirm is the Approve bar. Keyword assent helpers stay deleted."""

from __future__ import annotations

from pathlib import Path


def test_assent_module_is_gone() -> None:
    assert not Path("services/owner_copilot/assent.py").exists()


def test_system_prompt_forbids_keyword_assent() -> None:
    from services.owner_copilot.sol_seed import SOL_SEED_ADVANCED, SOL_SEED_DONT

    blob = SOL_SEED_ADVANCED + "\n".join(SOL_SEED_DONT)
    assert "ok" in blob
    assert "موافق" in blob
    assert "magic word" in blob
    assert "Approve" in blob
