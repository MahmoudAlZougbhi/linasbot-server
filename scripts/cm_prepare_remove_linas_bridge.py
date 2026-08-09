"""Post-migration: remove Linas legacy bridge after published CM cutover is verified.

This script does NOT deploy or publish. It only documents / validates readiness to flip
``CM_DISABLE_LINAS_LEGACY_BRIDGE=true`` and later delete bridge code paths.

Usage (read-only check):
  python scripts/cm_prepare_remove_linas_bridge.py --tenant linas
"""

from __future__ import annotations

import argparse
import json
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant", default="linas")
    args = parser.parse_args()

    from services.cm.constants import (
        cm_disable_linas_legacy_bridge,
        tenant_allows_legacy_bridge,
        tenant_has_published_cm,
        tenant_uses_cm_runtime,
    )
    from services.cm.version_store import load_published_content, read_published_pointer

    tenant_id = (args.tenant or "linas").strip()
    pointer = read_published_pointer(tenant_id)
    report: dict[str, object] = {
        "tenant_id": tenant_id,
        "has_published_pointer": pointer is not None,
        "tenant_uses_cm_runtime": tenant_uses_cm_runtime(tenant_id),
        "tenant_allows_legacy_bridge": tenant_allows_legacy_bridge(tenant_id),
        "cm_disable_linas_legacy_bridge": cm_disable_linas_legacy_bridge(),
        "ready_to_disable_bridge": False,
        "next_steps": [],
    }

    if pointer is None:
        report["next_steps"] = [
            "Publish Linas CM content first (scripts/cm_publish_tenant.py) with explicit production approval.",
            "Verify customer answers come from cm_runtime_pipeline (not legacy Marwa prompts).",
            "Then set CM_DISABLE_LINAS_LEGACY_BRIDGE=true and restart.",
            "After soak, delete tenant_allows_legacy_bridge call sites.",
        ]
        print(json.dumps(report, indent=2))
        return 1

    try:
        loaded_pointer, sections = load_published_content(tenant_id)
        report["content_version_id"] = loaded_pointer.content_version_id
        report["index_version_id"] = loaded_pointer.index_version_id
        report["assistant_name"] = (sections.get("ai_basics") or {}).get("assistant_name")
        report["clinic_name"] = (sections.get("ai_basics") or {}).get("clinic_name")
    except Exception as exc:
        report["load_error"] = str(exc)
        print(json.dumps(report, indent=2))
        return 1

    report["ready_to_disable_bridge"] = bool(tenant_has_published_cm(tenant_id) and tenant_uses_cm_runtime(tenant_id))
    report["next_steps"] = [
        "Confirm production traffic uses handler_path=cm_runtime_pipeline for Linas.",
        "Set CM_DISABLE_LINAS_LEGACY_BRIDGE=true (bridge becomes unreachable).",
        "Soak, then remove bridge code from text_handlers_respond / constants.",
    ]
    print(json.dumps(report, indent=2))
    return 0 if report["ready_to_disable_bridge"] else 1


if __name__ == "__main__":
    sys.exit(main())
