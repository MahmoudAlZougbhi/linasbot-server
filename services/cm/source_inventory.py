"""Owner-visible CM source inventory (metadata only — no content bodies / secrets)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from services.cm.constants import CM_SECTIONS, DEFAULT_TENANT_ID
from services.cm.paths import archive_dir, draft_dir, versions_dir
from services.cm.schemas import CareSection, FaqSection, KnowledgeSection
from services.cm.storage import get_draft
from services.cm.version_store import read_published_pointer
from storage.persistent_storage import get_data_root


def _draft_exists(tenant_id: str, section: str) -> bool:
    return (draft_dir(tenant_id) / f"{section}.json").is_file()


def _sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _file_meta(path: Path, *, category: str, destination: str) -> dict[str, Any]:
    return {
        "filename": path.name,
        "relative_hint": str(path),
        "size_bytes": path.stat().st_size if path.is_file() else 0,
        "sha256": _sha256_file(path),
        "format": path.suffix.lstrip(".") or "unknown",
        "category": category,
        "migration_destination": destination,
        "status": "present" if path.exists() else "missing",
    }


def build_source_inventory(*, tenant_id: str | None = None, data_root: Path | None = None) -> dict[str, Any]:
    """Build metadata ledger of CM drafts, published pointer, archives, and staged legacy files."""
    tid = (tenant_id or DEFAULT_TENANT_ID).strip() or DEFAULT_TENANT_ID
    root = Path(data_root) if data_root is not None else Path(get_data_root())

    pointer = read_published_pointer(tid)
    section_counts: dict[str, Any] = {}
    for section in CM_SECTIONS:
        present = _draft_exists(tid, section)
        if not present:
            section_counts[section] = {"draft_present": False}
            continue
        env = get_draft(section, tenant_id=tid, create_default=False)
        payload = env.payload if isinstance(env.payload, dict) else {}
        count: int | None = None
        status_counts: dict[str, int] = {}
        if section in {"knowledge", "care", "faq", "services", "branches", "dynamic_messages"}:
            raw_items = payload.get("items")
            items: list[Any] = list(raw_items) if isinstance(raw_items, list) else []
            count = len(items)
            for item in items:
                if not isinstance(item, dict):
                    continue
                status = str(item.get("status") or "active")
                status_counts[status] = status_counts.get(status, 0) + 1
        elif section == "handoff":
            raw_contacts = payload.get("contacts")
            raw_matrix = payload.get("matrix")
            contacts: list[Any] = list(raw_contacts) if isinstance(raw_contacts, list) else []
            matrix: list[Any] = list(raw_matrix) if isinstance(raw_matrix, list) else []
            count = len(contacts) + len(matrix)
        elif section == "restricted":
            raw_topics = payload.get("topics")
            topics: list[Any] = list(raw_topics) if isinstance(raw_topics, list) else []
            count = len(topics)
        elif section == "prices":
            raw_catalog = payload.get("catalog")
            raw_entries = payload.get("price_entries")
            catalog: list[Any] = list(raw_catalog) if isinstance(raw_catalog, list) else []
            entries: list[Any] = list(raw_entries) if isinstance(raw_entries, list) else []
            section_counts[section] = {
                "draft_present": True,
                "catalog_count": len(catalog),
                "price_entry_count": len(entries),
                "revision": env.revision,
            }
            continue
        section_counts[section] = {
            "draft_present": True,
            "item_count": count,
            "status_counts": status_counts,
            "revision": env.revision,
        }

    knowledge = KnowledgeSection.model_validate(get_draft("knowledge", tenant_id=tid, create_default=True).payload)
    care = CareSection.model_validate(get_draft("care", tenant_id=tid, create_default=True).payload)
    faq = FaqSection.model_validate(get_draft("faq", tenant_id=tid, create_default=True).payload)
    article_sources: list[dict[str, Any]] = []
    for kind, items in (("knowledge", knowledge.items), ("care", care.items)):
        for item in items:
            article_sources.append(
                {
                    "kind": kind,
                    "id": item.id,
                    "title": item.title,
                    "status": item.status,
                    "source_filename": item.source_filename,
                    "source_checksum": item.source_checksum,
                    "tags": list(item.tags),
                    "ui_visibility": "content-managers/" + ("care" if kind == "care" else "knowledge"),
                    "runtime_active": item.status not in {"archived", "restricted"},
                }
            )

    # Structured section inventory (metadata only).
    structured_sources: list[dict[str, Any]] = []
    for section_name in ("services", "branches", "dynamic_messages", "handoff", "prices", "ai_basics", "style"):
        if not _draft_exists(tid, section_name):
            continue
        env = get_draft(section_name, tenant_id=tid, create_default=False)
        section_payload: dict[str, Any] = env.payload if isinstance(env.payload, dict) else {}
        if section_name in {"services", "branches", "dynamic_messages"}:
            raw_items = section_payload.get("items")
            items_list: list[Any] = list(raw_items) if isinstance(raw_items, list) else []
            for item in items_list:
                if not isinstance(item, dict):
                    continue
                labels_raw = item.get("labels")
                labels: dict[str, Any] = labels_raw if isinstance(labels_raw, dict) else {}
                structured_sources.append(
                    {
                        "section": section_name,
                        "id": item.get("id"),
                        "title": labels.get("en") or item.get("name") or item.get("id"),
                        "available": item.get("available"),
                        "status": item.get("status"),
                    }
                )
        structured_sources.append(
            {
                "section": section_name,
                "id": f"{section_name}:policy_text",
                "policy_chars": len(str(section_payload.get("policy_text") or "")),
                "has_policy_text": bool(str(section_payload.get("policy_text") or "").strip()),
                "notes_chars": len(str(section_payload.get("notes") or "")),
                "has_notes": bool(str(section_payload.get("notes") or "").strip()),
            }
        )

    staging_legacy = root / "tenants" / tid / "cm" / "staging" / "prod_migration" / "legacy"
    staged_files: list[dict[str, Any]] = []
    if staging_legacy.is_dir():
        for path in sorted(staging_legacy.rglob("*")):
            if not path.is_file():
                continue
            dest = "knowledge"
            name = path.name.lower()
            if "price" in name:
                dest = "prices"
            elif "style" in name:
                dest = "style"
            elif "prompt" in name or "system" in name:
                dest = "ai_basics"
            elif "qa" in name or "faq" in name:
                dest = "faq"
            elif "dynamic" in name:
                dest = "dynamic_messages"
            elif path.parent.name == "knowledge_files":
                dest = "knowledge_or_care"
            staged_files.append(_file_meta(path, category="staged_legacy", destination=dest))

    archive_root = archive_dir(tid)
    archive_buckets: list[dict[str, Any]] = []
    scrub_root = archive_root / "restricted_scrub"
    if scrub_root.is_dir():
        for bucket in sorted(scrub_root.iterdir()):
            if not bucket.is_dir():
                continue
            files = []
            for path in sorted(bucket.glob("*.json")):
                files.append(
                    {
                        "filename": path.name,
                        "size_bytes": path.stat().st_size,
                        "sha256": _sha256_file(path),
                    }
                )
            archive_buckets.append({"bucket": bucket.name, "files": files, "status": "archived_restricted"})

    return {
        "tenant_id": tid,
        "data_root": str(root),
        "published_pointer": (
            {
                "content_version_id": pointer.content_version_id,
                "index_version_id": pointer.index_version_id,
            }
            if pointer
            else None
        ),
        "section_counts": section_counts,
        "article_sources": article_sources,
        "structured_sources": structured_sources,
        "faq_status_counts": {
            status: sum(1 for item in faq.items if item.status == status)
            for status in sorted({item.status for item in faq.items} | {"draft", "active", "archived", "restricted"})
        },
        "staged_legacy_files": staged_files,
        "restricted_scrub_archives": archive_buckets,
        "paths": {
            "draft_dir": str(draft_dir(tid)),
            "published_dir": str(draft_dir(tid).parent / "published"),
            "versions_dir": str(versions_dir(tid)),
            "archive_dir": str(archive_root),
        },
        "totals": {
            "article_source_rows": len(article_sources),
            "staged_legacy_files": len(staged_files),
            "restricted_scrub_buckets": len(archive_buckets),
            "faq_groups": len(faq.items),
            "restricted_articles": sum(1 for row in article_sources if row["status"] == "restricted"),
            "active_articles": sum(1 for row in article_sources if row["runtime_active"]),
        },
    }


def write_inventory_report(report: dict[str, Any], *, tenant_id: str | None = None) -> Path:
    tid = (tenant_id or DEFAULT_TENANT_ID).strip() or DEFAULT_TENANT_ID
    out_dir = archive_dir(tid) / "inventory"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "latest_inventory.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out_path
