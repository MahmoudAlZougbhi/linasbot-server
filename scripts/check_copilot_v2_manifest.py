#!/usr/bin/env python3
"""CI freshness check for System Copilot V2 capability manifest."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs" / "evidence" / "system_copilot_v2" / "capability_manifest.json"
TOOL_SCHEMAS = ROOT / "services" / "owner_copilot_v2" / "tool_schemas.py"
REGISTRY = ROOT / "services" / "system_knowledge_registry.py"


def main() -> int:
    if not MANIFEST.exists():
        print("FAIL: missing capability_manifest.json")
        return 1
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    errors: list[str] = []
    if data.get("owner_model") != "gpt-5.6-sol":
        errors.append("owner_model must be gpt-5.6-sol")
    if data.get("guest_model") != "gpt-5.6-sol":
        errors.append("guest_model must be gpt-5.6-sol")
    if data.get("guest_reasoning_effort") != "low":
        errors.append("guest_reasoning_effort must be low")
    if data.get("customer_hv_model") != "gpt-5.6-terra":
        errors.append("customer_hv_model must be gpt-5.6-terra")
    if data.get("customer_social_model") not in (None, "gpt-5.6-terra"):
        errors.append("customer_social_model must be gpt-5.6-terra when set")
    creative = next((c for c in data.get("capabilities", []) if c.get("id") == "creative_studio"), None)
    if not creative or creative.get("status") != "unavailable":
        errors.append("creative_studio must be unavailable in manifest")
    schemas = TOOL_SCHEMAS.read_text(encoding="utf-8")
    if "create_creative_draft" in schemas:
        errors.append("tool_schemas must not register create_creative_draft")
    registry = REGISTRY.read_text(encoding="utf-8")
    if 'feature="creative_studio"' in registry and 'status="unavailable"' not in registry:
        # soft: ensure cancelled wording present
        if "Cancelled" not in registry and "cancelled" not in registry:
            errors.append("system_knowledge_registry creative must be cancelled/unavailable")
    active = set(data.get("active_tools") or [])
    if "create_creative_draft" in active:
        errors.append("active_tools must not include creative tools")
    if "diagnose_meta_health" not in active:
        errors.append("active_tools missing diagnose_meta_health")
    if errors:
        print("FAIL:")
        for e in errors:
            print(" -", e)
        return 1
    print("OK: capability manifest fresh")
    return 0


if __name__ == "__main__":
    sys.exit(main())
