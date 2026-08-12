"""LOC split: cm prod_migration stage under 500 lines; public exports preserved."""

from __future__ import annotations

from pathlib import Path

from services.cm import prod_migration as prod_mod
from services.cm.prod_migration_stage import resolve_live_data_root, stage_live_data_for_migration


def _line_count(rel: str) -> int:
    return len(Path(rel).read_text(encoding="utf-8").splitlines())


def test_cm_prod_migration_modules_under_500_lines() -> None:
    assert _line_count("services/cm/prod_migration.py") < 500
    assert _line_count("services/cm/prod_migration_stage.py") < 500


def test_cm_prod_migration_preserves_public_api() -> None:
    assert prod_mod.resolve_live_data_root is resolve_live_data_root
    assert prod_mod.stage_live_data_for_migration is stage_live_data_for_migration
    assert callable(prod_mod.run_production_content_migration)
    assert callable(prod_mod.seed_owner_confirmed_structured_truth)
