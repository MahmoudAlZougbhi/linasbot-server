"""Restore CM records previously keyword-scrubbed into ``status=restricted``.

Owner rule (2026-08): topic-keyword scrub is revoked. Records tagged
``restricted_scrub`` (or archived under ``archive/restricted_scrub/``) must be
reactivated as ``active`` unless the owner explicitly re-restricts them.
"""

from __future__ import annotations

import json
from typing import Any

from services.cm.paths import archive_dir, ensure_cm_dirs
from services.cm.schemas import ArticleRecord, CareSection, FaqRecord, FaqSection, KnowledgeSection
from services.cm.storage import get_draft, put_draft


def _put_section(section: str, payload: dict[str, Any], *, tenant_id: str, updated_by: str) -> None:
    env = get_draft(section, tenant_id=tenant_id, create_default=True)
    put_draft(section, payload=payload, if_match=env.etag, tenant_id=tenant_id, updated_by=updated_by)


def _was_keyword_scrubbed(tags: list[str], notes: str | None) -> bool:
    if "restricted_scrub" in tags:
        return True
    note = notes or ""
    return "[restricted] Not used by AI — topic=" in note


def _strip_scrub_notes(notes: str | None) -> str | None:
    if not notes:
        return notes
    lines = [ln for ln in notes.splitlines() if "[restricted] Not used by AI — topic=" not in ln]
    cleaned = "\n".join(lines).strip()
    return cleaned or None


def _strip_scrub_tags(tags: list[str]) -> list[str]:
    out: list[str] = []
    for tag in tags:
        if tag == "restricted_scrub" or tag.startswith("topic:"):
            continue
        out.append(tag)
    return out


def restore_keyword_scrubbed_content(*, tenant_id: str, updated_by: str) -> dict[str, Any]:
    """Reactivate FAQ/knowledge/care items marked by the revoked keyword scrub.

    Also merges any records still only present in ``archive/restricted_scrub/*/``
    JSON dumps (faq_removed / knowledge_removed / care_removed) that are missing
    from drafts.
    """
    ensure_cm_dirs(tenant_id)
    report: dict[str, Any] = {
        "faq_restored_ids": [],
        "knowledge_restored_ids": [],
        "care_restored_ids": [],
        "archive_merged_ids": [],
    }

    faq_env = get_draft("faq", tenant_id=tenant_id, create_default=True)
    faq = FaqSection.model_validate(faq_env.payload)
    restored_faq: list[FaqRecord] = []
    for item in faq.items:
        if item.status == "restricted" and _was_keyword_scrubbed(list(item.tags), item.notes):
            report["faq_restored_ids"].append(item.qa_group_id)
            restored_faq.append(
                item.model_copy(
                    update={
                        "status": "active",
                        "tags": _strip_scrub_tags(list(item.tags)),
                        "notes": _strip_scrub_notes(item.notes),
                    }
                )
            )
        else:
            restored_faq.append(item)

    by_faq = {item.qa_group_id: item for item in restored_faq}
    for archived in _load_scrub_archive_records(tenant_id, "faq_removed.json"):
        group_id = str(archived.get("qa_group_id") or "")
        if not group_id or group_id in by_faq:
            continue
        faq_record = FaqRecord.model_validate(archived)
        by_faq[group_id] = faq_record.model_copy(
            update={
                "status": "active",
                "tags": _strip_scrub_tags(list(faq_record.tags)),
                "notes": _strip_scrub_notes(faq_record.notes),
            }
        )
        report["archive_merged_ids"].append(group_id)
        report["faq_restored_ids"].append(group_id)
    _put_section(
        "faq",
        FaqSection(
            items=list(by_faq.values()),
            notes=faq.notes,
            smart_answer_languages=faq.smart_answer_languages,
        ).model_dump(mode="json"),
        tenant_id=tenant_id,
        updated_by=updated_by,
    )

    for section_name, key, removed_name in (
        ("knowledge", "knowledge_restored_ids", "knowledge_removed.json"),
        ("care", "care_restored_ids", "care_removed.json"),
    ):
        env = get_draft(section_name, tenant_id=tenant_id, create_default=True)
        if section_name == "knowledge":
            section_model: KnowledgeSection | CareSection = KnowledgeSection.model_validate(env.payload)
        else:
            section_model = CareSection.model_validate(env.payload)
        restored_articles: list[ArticleRecord] = []
        for article in section_model.items:
            if article.status == "restricted" and _was_keyword_scrubbed(list(article.tags), article.notes):
                report[key].append(article.id)
                restored_articles.append(
                    article.model_copy(
                        update={
                            "status": "active",
                            "tags": _strip_scrub_tags(list(article.tags)),
                            "notes": _strip_scrub_notes(article.notes),
                        }
                    )
                )
            else:
                restored_articles.append(article)
        by_article_id: dict[str, ArticleRecord] = {item.id: item for item in restored_articles}
        for archived in _load_scrub_archive_records(tenant_id, removed_name):
            article_id = str(archived.get("id") or "")
            if not article_id or article_id in by_article_id:
                continue
            article_record = ArticleRecord.model_validate(archived)
            by_article_id[article_id] = article_record.model_copy(
                update={
                    "status": "active",
                    "tags": _strip_scrub_tags(list(article_record.tags)),
                    "notes": _strip_scrub_notes(article_record.notes),
                }
            )
            report["archive_merged_ids"].append(article_id)
            report[key].append(article_id)
        if section_name == "knowledge":
            payload = KnowledgeSection(items=list(by_article_id.values()), notes=section_model.notes).model_dump(
                mode="json"
            )
        else:
            payload = CareSection(items=list(by_article_id.values()), notes=section_model.notes).model_dump(mode="json")
        _put_section(section_name, payload, tenant_id=tenant_id, updated_by=updated_by)

    return report


def _load_scrub_archive_records(tenant_id: str, filename: str) -> list[dict[str, Any]]:
    scrub_root = archive_dir(tenant_id) / "restricted_scrub"
    if not scrub_root.is_dir():
        return []
    records: list[dict[str, Any]] = []
    for bucket in sorted(scrub_root.iterdir()):
        path = bucket / filename
        if not path.is_file():
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict):
                    records.append(item)
    return records
