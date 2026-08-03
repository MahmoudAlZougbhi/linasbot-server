"""Static audit: no Lina-specific / body-part pricing engine in platform code."""

from __future__ import annotations

from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

# Forbidden platform symbols — pricing must stay generic.
FORBIDDEN_SYMBOLS: tuple[str, ...] = (
    "BodyPartPricingEngine",
    "body_part_pricing",
    "LinasPricingEngine",
    "linas_discount_threshold",
    "LINAS_PRICE_",
    "class BodyPartPrice",
)

# Paths scanned for forbidden pricing architecture (not booking CRM body_part APIs).
SCAN_GLOBS: tuple[str, ...] = (
    "services/cm/**/*.py",
    "modules/cm_*.py",
    "dashboard/src/pages/content-managers/**/*.{js,jsx}",
)


def audit_no_linas_pricing_in_code(*, root: Path | None = None) -> dict[str, Any]:
    base = root or _PROJECT_ROOT
    findings: list[dict[str, Any]] = []
    files: list[Path] = []
    for pattern in SCAN_GLOBS:
        files.extend(base.glob(pattern))
    skip_names = {"audit.py"}  # this file lists forbidden symbols by design
    for path in sorted(set(files)):
        if not path.is_file() or path.name in skip_names:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for symbol in FORBIDDEN_SYMBOLS:
            if symbol in text:
                findings.append(
                    {
                        "path": str(path.relative_to(base)),
                        "symbol": symbol,
                    }
                )
    return {
        "ok": len(findings) == 0,
        "scanned_files": len({p for p in files if p.is_file() and p.name not in skip_names}),
        "findings": findings,
        "note": (
            "Pass means no Lina-/body-part-named pricing engine types exist under CM. "
            "Tenant catalog may still use item_type='body_area' as data."
        ),
    }
