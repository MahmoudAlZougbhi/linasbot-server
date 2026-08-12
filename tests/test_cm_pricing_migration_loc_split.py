"""LOC split: cm pricing migration extract under 500 lines; public exports preserved."""

from __future__ import annotations

from pathlib import Path

from services.cm.pricing import migration as migration_mod
from services.cm.pricing.migration_extract import (
    extract_price_rows_from_json_obj,
    extract_price_rows_from_json_obj_with_ambiguous,
    extract_price_rows_from_text,
)


def _line_count(rel: str) -> int:
    return len(Path(rel).read_text(encoding="utf-8").splitlines())


def test_cm_pricing_migration_modules_under_500_lines() -> None:
    assert _line_count("services/cm/pricing/migration.py") < 500
    assert _line_count("services/cm/pricing/migration_extract.py") < 500


def test_cm_pricing_migration_preserves_public_api() -> None:
    assert migration_mod.extract_price_rows_from_text is extract_price_rows_from_text
    assert migration_mod.extract_price_rows_from_json_obj is extract_price_rows_from_json_obj
    assert (
        migration_mod.extract_price_rows_from_json_obj_with_ambiguous is extract_price_rows_from_json_obj_with_ambiguous
    )
    assert callable(migration_mod.build_prices_section_from_rows)
    assert callable(migration_mod.migrate_staged_price_files_to_catalog)
    assert callable(migration_mod.seed_example_discount_rule_subtotal)
