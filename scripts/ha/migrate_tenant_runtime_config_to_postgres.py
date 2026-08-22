#!/usr/bin/env python3
"""Idempotent migration: node-local tenant runtime config -> Postgres SoT."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from services.cm.constants import CM_SECTIONS, DEFAULT_TENANT_ID
from services.cm.paths import draft_dir, published_pointer_path
from services.cm.schemas import PublishedPointer, SectionDraftEnvelope
from services.cm.atomic_io import read_json_object
from services.cm.version_store import load_published_content, read_published_pointer
from services.meta_app_registry import binding_asset_key
from services.meta_comment_reply_settings import list_comment_reply_settings
from services.tenant_runtime_config_service import (
    mark_migration_applied,
    migration_is_applied,
    postgres_enabled,
    save_actions_payload,
    save_comment_asset_setting,
    save_draft_envelope,
)


def _inventory_tenant(tenant_id: str) -> dict[str, Any]:
    pointer = read_published_pointer(tenant_id)
    drafts: dict[str, Any] = {}
    for section in CM_SECTIONS:
        path = draft_dir(tenant_id) / f"{section}.json"
        if path.is_file():
            drafts[section] = read_json_object(path)
    comment_settings = [row.public_dict() for row in list_comment_reply_settings(tenant_id)]
    return {
        "pointer": pointer.model_dump(mode="json") if pointer else None,
        "draft_sections": sorted(drafts.keys()),
        "comment_settings_count": len(comment_settings),
    }


def migrate_tenant(*, tenant_id: str, dry_run: bool = True) -> dict[str, Any]:
    if not postgres_enabled():
        raise RuntimeError("Postgres backend required for migration")
    if migration_is_applied(tenant_id=tenant_id):
        return {"tenant_id": tenant_id, "skipped": True, "reason": "already_applied"}
    inventory = _inventory_tenant(tenant_id)
    audit: dict[str, Any] = {"inventory": inventory, "decisions": []}
    pointer = read_published_pointer(tenant_id)
    if pointer is not None:
        _ptr, sections = load_published_content(tenant_id)
        actions_payload = dict(sections.get("actions") or {})
        audit["decisions"].append({"kind": "published_actions", "source": "local_pointer"})
        if not dry_run:
            save_actions_payload(
                tenant_id=tenant_id,
                actions_payload=actions_payload,
                expected_published_revision=None,
                published_meta={
                    "content_version_id": pointer.content_version_id,
                    "index_version_id": pointer.index_version_id or "",
                    "checksums": dict(pointer.checksums or {}),
                    "embedding_provider": pointer.embedding_provider,
                    "embedding_model": pointer.embedding_model,
                    "embedding_dimensions": pointer.embedding_dimensions,
                    "embedding_version": pointer.embedding_version,
                    "schema_version": pointer.schema_version,
                    "published_at": pointer.updated_at.timestamp() if pointer.updated_at else time.time(),
                },
            )
    for section in CM_SECTIONS:
        path = draft_dir(tenant_id) / f"{section}.json"
        if not path.is_file():
            continue
        envelope = SectionDraftEnvelope.model_validate(read_json_object(path))
        audit["decisions"].append({"kind": "draft", "section": section, "revision": envelope.revision})
        if not dry_run:
            save_draft_envelope(envelope=envelope, expected_revision=-1)
    for row in list_comment_reply_settings(tenant_id):
        audit["decisions"].append({"kind": "comment_asset", "asset_key": row.asset_key, "enabled": row.enabled})
        if not dry_run:
            save_comment_asset_setting(
                tenant_id=tenant_id,
                asset_key=row.asset_key,
                app_key=row.app_key,
                channel=row.channel,
                asset_id=row.asset_id,
                enabled=row.enabled,
                instructions=row.instructions,
                expected_revision=None,
            )
    backup_path = Path(f"/tmp/tenant_runtime_config_backup_{tenant_id}_{int(time.time())}.json")
    backup_path.write_text(json.dumps(inventory, indent=2), encoding="utf-8")
    audit["backup_path"] = str(backup_path)
    if not dry_run:
        mark_migration_applied(tenant_id=tenant_id, audit=audit)
    return {"tenant_id": tenant_id, "dry_run": dry_run, "audit": audit}


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate tenant runtime config to Postgres")
    parser.add_argument("--tenant", default=DEFAULT_TENANT_ID)
    parser.add_argument("--apply", action="store_true", help="Apply migration (default dry-run)")
    args = parser.parse_args()
    result = migrate_tenant(tenant_id=args.tenant, dry_run=not args.apply)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
