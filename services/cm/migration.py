"""Copy-first migration of legacy/fixture content into CM drafts (plan §10 / Phase 4).

Writes are strictly confined to ``{DATA_ROOT}/tenants/{tenant_id}/cm/{draft,archive}``.
Nothing here writes to production stores (qa_pairs.jsonl, content-files, settings) or
outside the tenant CM subtree. No structured facts are invented from free text — legacy
unstructured blobs are archived and mirrored as flagged Knowledge notes, never turned into
authoritative Price/Service rows.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar, cast

from pydantic import BaseModel

from services.cm.atomic_io import atomic_write_bytes
from services.cm.conflict_validation import validate_restricted_conflicts
from services.cm.constants import CM_SECTIONS
from services.cm.paths import archive_dir, ensure_cm_dirs
from services.cm.schemas import (
    ArticleRecord,
    CareSection,
    FaqRecord,
    FaqSection,
    FaqVariant,
    HandoffContact,
    HandoffMatrixRow,
    HandoffPolicy,
    KnowledgeSection,
    LangCode,
)
from services.cm.storage import ConflictError, get_draft, put_draft
from services.language_detection_service import language_detection_service
from services.social_contact_routing import DEFAULT_SOCIAL_WHATSAPP_CONTACTS

_MAX_RETRIES = 5

_TListModel = TypeVar("_TListModel", bound=BaseModel)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _deterministic_id(*parts: str) -> str:
    """Stable id derived from content so re-running migration is idempotent."""
    digest = hashlib.sha256("::".join(parts).encode("utf-8")).hexdigest()[:12]
    return f"legacy_{digest}"


def _merge_list_section(
    section: str,
    *,
    tenant_id: str,
    updated_by: str,
    build_items: Callable[[list[Any]], list[Any]],
    model_cls: type[_TListModel],
) -> _TListModel:
    """Optimistic-concurrency merge for a CM section shaped as ``{items: [...], notes}``."""
    last_error: ConflictError | None = None
    for _ in range(_MAX_RETRIES):
        env = get_draft(section, tenant_id=tenant_id, create_default=True)
        current = model_cls.model_validate(env.payload)  # type: ignore[attr-defined]
        new_items = build_items(list(current.items))  # type: ignore[attr-defined]
        merged = model_cls.model_validate({"items": new_items, "notes": getattr(current, "notes", None)})
        new_payload = cast(dict[str, object], merged.model_dump(mode="json"))
        try:
            updated_env = put_draft(
                section,
                payload=new_payload,
                if_match=env.etag,
                tenant_id=tenant_id,
                updated_by=updated_by,
            )
            return cast(_TListModel, model_cls.model_validate(updated_env.payload))
        except ConflictError as exc:
            last_error = exc
            continue
    raise RuntimeError(f"Could not merge into '{section}' draft after retries: {last_error}")


def _migrate_faq(qa_rows: list[dict[str, Any]], *, tenant_id: str, updated_by: str) -> list[FaqRecord]:
    grouped: dict[str, FaqRecord] = {}
    for row in qa_rows:
        question = str(row.get("question") or "").strip()
        answer = str(row.get("answer") or "").strip()
        if not question or not answer:
            continue
        language = language_detection_service.normalize_training_language(row.get("language"), default="ar")
        group_id = str(row.get("qa_group_id") or "").strip() or _deterministic_id("faq", question, language)
        variant = FaqVariant(language=cast(LangCode, language), question=question, answer=answer)

        existing = grouped.get(group_id)
        if existing is None:
            grouped[group_id] = FaqRecord(
                qa_group_id=group_id,
                variants=[variant],
                tags=["legacy_migration"],
                status="active",
            )
        else:
            variants = [v for v in existing.variants if v.language != language]
            variants.append(variant)
            grouped[group_id] = FaqRecord(
                qa_group_id=group_id,
                variants=variants,
                tags=existing.tags,
                notes=existing.notes,
                status=existing.status if existing.status != "draft" else "active",
            )

    records = list(grouped.values())

    def _build(existing_items: list[FaqRecord]) -> list[FaqRecord]:
        by_id = {item.qa_group_id: item for item in existing_items}
        for record in records:
            by_id[record.qa_group_id] = record
        return list(by_id.values())

    _merge_list_section("faq", tenant_id=tenant_id, updated_by=updated_by, build_items=_build, model_cls=FaqSection)
    return records


def _migrate_knowledge_and_care(
    *,
    price_list_text: str | None,
    knowledge_base_text: str | None,
    knowledge_files: list[dict[str, Any]],
    tenant_id: str,
    updated_by: str,
) -> tuple[list[ArticleRecord], list[ArticleRecord]]:
    knowledge_items: list[ArticleRecord] = []
    care_items: list[ArticleRecord] = []

    if knowledge_base_text and knowledge_base_text.strip():
        knowledge_items.append(
            ArticleRecord(
                id=_deterministic_id("knowledge_base"),
                title="Legacy knowledge base",
                body=knowledge_base_text,
                tags=["legacy_migration", "unstructured"],
                language="",
                audience="general",
                category="foundation",
                status="active",
                source_filename="knowledge_base.txt",
                notes="Migrated verbatim from legacy knowledge_base.txt; review before authoritative use.",
            )
        )

    if price_list_text and price_list_text.strip():
        knowledge_items.append(
            ArticleRecord(
                id=_deterministic_id("price_list"),
                title="Legacy price list (unstructured)",
                body=price_list_text,
                tags=["legacy_migration", "unstructured", "needs_price_structuring"],
                language="",
                audience="general",
                category="pricing_source",
                status="active",
                source_filename="price_list.txt",
                notes="Legacy free-text pricing note; NOT authoritative. Use the structured Prices section for exact amounts.",
            )
        )

    for entry in knowledge_files:
        tags = [str(t) for t in (entry.get("tags") or [])]
        if "legacy_migration" not in tags:
            tags = [*tags, "legacy_migration"]
        audience = entry.get("audience") if entry.get("audience") in {"men", "women", "general"} else "general"
        source_name = str(entry.get("filename") or entry.get("source") or entry.get("id") or "")
        raw_status = str(entry.get("status") or "active").strip().lower()
        # Honor explicit source status only; never infer restricted from topic/filename keywords.
        status = raw_status if raw_status in {"draft", "active", "archived", "restricted"} else "active"
        article = ArticleRecord(
            id=_deterministic_id("knowledge_file", str(entry.get("id") or entry.get("title") or "")),
            title=str(entry.get("title") or ""),
            body=str(entry.get("content") or entry.get("body") or ""),
            tags=tags,
            language=str(entry.get("language") or ""),
            audience=audience,  # type: ignore[arg-type]
            category=str(entry.get("category") or ""),
            status=status,  # type: ignore[arg-type]
            source_filename=source_name or None,
            source_checksum=str(entry.get("checksum") or "") or None,
            notes=None,
        )
        from services.cm.section_classifier import classify_article

        classification = classify_article(
            article_id=article.id,
            title=article.title,
            body=article.body,
            tags=tags,
            source_filename=article.source_filename,
            source_checksum=article.source_checksum,
            category=article.category,
        )
        if classification.move_to_care:
            care_items.append(article)
        else:
            knowledge_items.append(article)

    def _build_knowledge(existing_items: list[ArticleRecord]) -> list[ArticleRecord]:
        by_id = {item.id: item for item in existing_items}
        for item in knowledge_items:
            by_id[item.id] = item
        return list(by_id.values())

    def _build_care(existing_items: list[ArticleRecord]) -> list[ArticleRecord]:
        by_id = {item.id: item for item in existing_items}
        for item in care_items:
            by_id[item.id] = item
        return list(by_id.values())

    if knowledge_items:
        _merge_list_section(
            "knowledge",
            tenant_id=tenant_id,
            updated_by=updated_by,
            build_items=_build_knowledge,
            model_cls=KnowledgeSection,
        )
    if care_items:
        _merge_list_section(
            "care", tenant_id=tenant_id, updated_by=updated_by, build_items=_build_care, model_cls=CareSection
        )

    return knowledge_items, care_items


def _classify_contact_key(key: str) -> tuple[str | None, str, str | None]:
    upper = key.upper()
    branch_id = "beirut" if "BEIRUT" in upper else ("antelias" if "ANTELIAS" in upper else None)
    if "FEMALE" in upper:
        gender = "female"
    elif upper.endswith("_MALE"):
        gender = "male"
    else:
        gender = "any"
    topic_id = "tattoo_removal" if "TATTOO_REMOVAL" in upper else None
    return branch_id, gender, topic_id


def _migrate_handoff(*, tenant_id: str, updated_by: str) -> HandoffPolicy:
    contacts: list[HandoffContact] = []
    matrix: list[HandoffMatrixRow] = []
    for key, phone in DEFAULT_SOCIAL_WHATSAPP_CONTACTS.items():
        branch_id, gender, topic_id = _classify_contact_key(key)
        contact_id = key.lower()
        contacts.append(
            HandoffContact(
                id=contact_id,
                phone_e164=phone,
                label=key.replace("_", " ").title(),
                branch_id=branch_id,
                gender=gender,  # type: ignore[arg-type]
                topic_id=topic_id,
                notes="Migrated from social_contact_routing.DEFAULT_SOCIAL_WHATSAPP_CONTACTS (draft only; runtime cutover is Phase 8).",
            )
        )
        matrix.append(
            HandoffMatrixRow(
                id=f"row_{contact_id}",
                contact_id=contact_id,
                service_id=None,
                topic_id=topic_id,
                branch_id=branch_id,
                gender=gender,  # type: ignore[arg-type]
                enabled=True,
            )
        )

    last_error: ConflictError | None = None
    for _ in range(_MAX_RETRIES):
        env = get_draft("handoff", tenant_id=tenant_id, create_default=True)
        current = HandoffPolicy.model_validate(env.payload)
        contacts_by_id = {c.id: c for c in current.contacts}
        for contact in contacts:
            contacts_by_id[contact.id] = contact
        matrix_by_id = {m.id: m for m in current.matrix}
        for row in matrix:
            matrix_by_id[row.id] = row
        new_payload = HandoffPolicy(
            contacts=list(contacts_by_id.values()),
            matrix=list(matrix_by_id.values()),
            notes=current.notes,
        ).model_dump(mode="json")
        try:
            updated_env = put_draft(
                "handoff", payload=new_payload, if_match=env.etag, tenant_id=tenant_id, updated_by=updated_by
            )
            return HandoffPolicy.model_validate(updated_env.payload)
        except ConflictError as exc:
            last_error = exc
            continue
    raise RuntimeError(f"Could not merge into 'handoff' draft after retries: {last_error}")


def _archive_legacy_files(files: list[Path], source_root: Path, *, tenant_id: str) -> list[dict[str, Any]]:
    ensure_cm_dirs(tenant_id)
    out_dir = archive_dir(tenant_id) / "legacy_migration"
    entries: list[dict[str, Any]] = []
    for path in sorted(files):
        rel = path.relative_to(source_root)
        data = path.read_bytes()
        checksum = _sha256_bytes(data)
        dest = out_dir / rel
        atomic_write_bytes(dest, data)
        entries.append({"rel": str(rel), "sha256": checksum, "size": len(data), "archived_path": str(dest)})
    return entries


def _detect_conflicts(*, tenant_id: str) -> list[dict[str, Any]]:
    drafts: dict[str, dict[str, Any]] = {}
    for section in CM_SECTIONS:
        env = get_draft(section, tenant_id=tenant_id, create_default=True)
        drafts[section] = dict(env.payload)
    failures = validate_restricted_conflicts(
        restricted=drafts.get("restricted") or {},
        services=drafts.get("services"),
        prices=drafts.get("prices"),
        faq=drafts.get("faq"),
        knowledge=drafts.get("knowledge"),
        handoff=drafts.get("handoff"),
    )
    return [failure.model_dump(mode="json") for failure in failures]


def migrate_legacy_fixture(
    *,
    source_root: str | Path,
    tenant_id: str,
    updated_by: str = "migration",
) -> dict[str, Any]:
    """Migrate a legacy/fixture tree into CM drafts for ``tenant_id``. Idempotent by content id."""
    root = Path(source_root)
    if not root.is_dir():
        raise FileNotFoundError(f"Migration source root not found: {root}")

    legacy_dir = root / "legacy"
    qa_path = legacy_dir / "qa_pairs.jsonl"
    price_path = legacy_dir / "price_list.txt"
    kb_path = legacy_dir / "knowledge_base.txt"
    knowledge_files_dir = legacy_dir / "knowledge_files"

    qa_rows: list[dict[str, Any]] = []
    if qa_path.exists():
        for line in qa_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped:
                qa_rows.append(json.loads(stripped))

    price_text = price_path.read_text(encoding="utf-8") if price_path.exists() else None
    kb_text = kb_path.read_text(encoding="utf-8") if kb_path.exists() else None

    knowledge_file_entries: list[dict[str, Any]] = []
    if knowledge_files_dir.is_dir():
        for file_path in sorted(knowledge_files_dir.glob("*.json")):
            try:
                raw_bytes = file_path.read_bytes()
                payload = json.loads(raw_bytes.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            if not isinstance(payload, dict):
                continue
            payload.setdefault("filename", file_path.name)
            payload.setdefault("checksum", _sha256_bytes(raw_bytes))
            knowledge_file_entries.append(payload)

    faq_records = _migrate_faq(qa_rows, tenant_id=tenant_id, updated_by=updated_by)
    knowledge_items, care_items = _migrate_knowledge_and_care(
        price_list_text=price_text,
        knowledge_base_text=kb_text,
        knowledge_files=knowledge_file_entries,
        tenant_id=tenant_id,
        updated_by=updated_by,
    )
    handoff_policy = _migrate_handoff(tenant_id=tenant_id, updated_by=updated_by)

    legacy_files = [p for p in legacy_dir.rglob("*") if p.is_file()] if legacy_dir.is_dir() else []
    archived = _archive_legacy_files(legacy_files, root, tenant_id=tenant_id)

    conflicts = _detect_conflicts(tenant_id=tenant_id)

    return {
        "tenant_id": tenant_id,
        "source_root": str(root),
        "faq_groups_imported": len(faq_records),
        "knowledge_articles_imported": len(knowledge_items),
        "care_articles_imported": len(care_items),
        "handoff_contacts_imported": len(handoff_policy.contacts),
        "archived_files": archived,
        "conflicts": conflicts,
        "conflict_count": len(conflicts),
    }
