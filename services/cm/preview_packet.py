"""Safe Testing Lab preview packets (no customer-history writes)."""

from __future__ import annotations

import json
from typing import Any

from services.cm.constants import CM_SECTIONS, DEFAULT_TENANT_ID
from services.cm.paths import ensure_cm_dirs, published_pointer_path, versions_dir
from services.cm.storage import get_draft


def list_versions(tenant_id: str | None = None) -> list[dict[str, Any]]:
    ensure_cm_dirs(tenant_id)
    root = versions_dir(tenant_id)
    if not root.exists():
        return []
    versions: list[dict[str, Any]] = []
    for child in sorted(root.iterdir(), reverse=True):
        if not child.is_dir():
            continue
        manifest = child / "manifest.json"
        if not manifest.exists():
            versions.append({"version_id": child.name})
            continue
        try:
            meta = json.loads(manifest.read_text(encoding="utf-8"))
            if isinstance(meta, dict):
                meta.setdefault("version_id", child.name)
                versions.append(meta)
            else:
                versions.append({"version_id": child.name})
        except (OSError, json.JSONDecodeError):
            versions.append({"version_id": child.name})
    return versions


def read_published_pointer(tenant_id: str | None = None) -> dict[str, Any] | None:
    path = published_pointer_path(tenant_id)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def build_preview_packet(
    *,
    source: str = "draft",
    tenant_id: str | None = None,
) -> dict[str, Any]:
    """Build a Lab-safe packet from draft or published pointer (never mutates prod history)."""
    src = (source or "draft").strip().lower()
    if src not in {"draft", "published"}:
        raise ValueError("source must be 'draft' or 'published'")

    tid = (tenant_id or DEFAULT_TENANT_ID).strip() or DEFAULT_TENANT_ID
    pointer = read_published_pointer(tid)

    if src == "published":
        version_id = (pointer or {}).get("content_version_id") or (pointer or {}).get("version_id")
        return {
            "source": "published",
            "tenant_id": tid,
            "version_id": version_id,
            "pointer": pointer,
            "sections": {},
            "safe": True,
            "customer_impact": False,
            "note": "No published CM version is active yet."
            if not version_id
            else "Published pointer only; full payload load comes in a later phase.",
        }

    sections: dict[str, Any] = {}
    for name in CM_SECTIONS:
        env = get_draft(name, tenant_id=tid, create_default=True)
        sections[name] = {
            "revision": env.revision,
            "etag": env.etag,
            "updated_at": env.updated_at.isoformat(),
            "payload": env.payload,
        }

    return {
        "source": "draft",
        "tenant_id": tid,
        "version_id": None,
        "pointer": pointer,
        "sections": sections,
        "safe": True,
        "customer_impact": False,
    }
