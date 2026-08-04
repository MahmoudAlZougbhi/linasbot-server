"""Idempotent redistribution of misplaced CM Knowledge articles into owner sections.

Copy-first: original words are preserved in the destination (and archived Knowledge
rows retain bodies for provenance). Never invents amounts/hours/phones. Never
auto-restricts by topic keywords.
"""

from __future__ import annotations

import json
from typing import Any

from services.cm.paths import archive_dir
from services.cm.schemas import (
    AiBasics,
    ArticleRecord,
    BranchesSection,
    CareSection,
    DynamicMessageRecord,
    DynamicMessagesSection,
    HandoffPolicy,
    KnowledgeSection,
    PricesSection,
    ServiceRecord,
    ServicesSection,
    StylePolicy,
)
from services.cm.section_classifier import (
    ArticleClassification,
    classify_article,
    detect_service_availability_conflicts,
)
from services.cm.storage import get_draft, put_draft

_REDISTRIBUTED_TAG = "cm_redistributed"
_PROVENANCE_PREFIX = "--- redistributed from "


def _provenance_block(article: ArticleRecord, classification: ArticleClassification) -> str:
    header = (
        f"{_PROVENANCE_PREFIX}id={article.id} "
        f"file={article.source_filename or ''} "
        f"checksum={article.source_checksum or ''} "
        f"title={article.title} "
        f"targets={','.join(classification.targets)} ---"
    )
    return f"{header}\n{article.body}".strip()


def _notes_already_contain(notes: str | None, article: ArticleRecord) -> bool:
    text = notes or ""
    if article.source_checksum and article.source_checksum in text:
        return True
    marker = f"id={article.id} "
    return marker in text


def _append_notes(existing: str | None, block: str) -> str:
    if not existing or not existing.strip():
        return block
    if block in existing:
        return existing
    return f"{existing.rstrip()}\n\n{block}".strip()


def _put(section: str, payload: dict[str, Any], *, tenant_id: str, updated_by: str) -> None:
    env = get_draft(section, tenant_id=tenant_id, create_default=True)
    put_draft(section, payload=payload, if_match=env.etag, tenant_id=tenant_id, updated_by=updated_by)


def _merge_service(existing: ServiceRecord | None, derived: ServiceRecord) -> ServiceRecord:
    if existing is None:
        return derived
    # Preserve both availability claims via notes when they conflict; do not silently overwrite.
    notes = existing.notes or ""
    if existing.available != derived.available:
        conflict_note = (
            f"AVAILABILITY CONFLICT: existing={existing.available} vs derived={derived.available}. "
            f"Both preserved; owner must resolve. Derived note: {derived.notes or ''}"
        )
        notes = _append_notes(notes, conflict_note)
        # Keep existing availability bit; conflict is surfaced in report/notes.
        available = existing.available
    else:
        available = existing.available
        if derived.notes:
            notes = _append_notes(notes, derived.notes)
    aliases = list(dict.fromkeys([*existing.aliases, *derived.aliases]))
    labels = existing.labels
    if not (labels.en or labels.ar or labels.fr):
        labels = derived.labels
    return ServiceRecord(
        id=existing.id,
        labels=labels,
        available=available,
        category=existing.category or derived.category,
        aliases=aliases,
        audience=existing.audience or derived.audience,
        notes=notes or None,
    )


def redistribute_knowledge_draft(
    *,
    tenant_id: str,
    updated_by: str = "cm_section_redistribution",
) -> dict[str, Any]:
    """Re-home misplaced Knowledge articles into the correct CM sections (idempotent)."""
    knowledge_env = get_draft("knowledge", tenant_id=tenant_id, create_default=True)
    knowledge = KnowledgeSection.model_validate(knowledge_env.payload)
    care_env = get_draft("care", tenant_id=tenant_id, create_default=True)
    care = CareSection.model_validate(care_env.payload)
    services_env = get_draft("services", tenant_id=tenant_id, create_default=True)
    services = ServicesSection.model_validate(services_env.payload)
    branches_env = get_draft("branches", tenant_id=tenant_id, create_default=True)
    branches = BranchesSection.model_validate(branches_env.payload)
    handoff_env = get_draft("handoff", tenant_id=tenant_id, create_default=True)
    handoff = HandoffPolicy.model_validate(handoff_env.payload)
    prices_env = get_draft("prices", tenant_id=tenant_id, create_default=True)
    prices = PricesSection.model_validate(prices_env.payload)
    style_env = get_draft("style", tenant_id=tenant_id, create_default=True)
    style = StylePolicy.model_validate(style_env.payload)
    ai_env = get_draft("ai_basics", tenant_id=tenant_id, create_default=True)
    ai = AiBasics.model_validate(ai_env.payload)
    dyn_env = get_draft("dynamic_messages", tenant_id=tenant_id, create_default=True)
    dyn = DynamicMessagesSection.model_validate(dyn_env.payload)

    services_by_id = {item.id: item for item in services.items}
    care_by_id = {item.id: item for item in care.items}
    dyn_by_id = {item.id: item for item in dyn.items}

    ledger: list[dict[str, Any]] = []
    classifications: list[ArticleClassification] = []
    next_knowledge: list[ArticleRecord] = []

    for article in knowledge.items:
        # Already-archived redistributed rows: keep as-is, still emit ledger for parity.
        if article.status == "archived" and _REDISTRIBUTED_TAG in article.tags:
            next_knowledge.append(article)
            target_tags = [t.split("target:", 1)[1] for t in article.tags if t.startswith("target:")]
            ledger.append(
                {
                    "source_id": article.id,
                    "title": article.title,
                    "source_filename": article.source_filename,
                    "source_checksum": article.source_checksum,
                    "targets": target_tags or ["archived"],
                    "derived_ids": [],
                    "keep_in_knowledge_active": False,
                    "archive_from_knowledge": True,
                    "rationale": "already_redistributed_archived",
                }
            )
            continue

        classification = classify_article(
            article_id=article.id,
            title=article.title,
            body=article.body,
            tags=list(article.tags),
            source_filename=article.source_filename,
            source_checksum=article.source_checksum,
            category=article.category,
        )
        classifications.append(classification)
        block = _provenance_block(article, classification)
        derived_ids: list[str] = []

        for spec in classification.service_derivations:
            derived = ServiceRecord(
                id=spec.id,
                labels=spec.labels,
                available=spec.available,
                category=spec.category,
                aliases=list(spec.aliases),
                audience=spec.audience,
                notes=spec.notes,
            )
            services_by_id[spec.id] = _merge_service(services_by_id.get(spec.id), derived)
            derived_ids.append(f"service:{spec.id}")

        if classification.move_to_care:
            care_article = ArticleRecord(
                id=article.id,
                title=article.title,
                body=article.body,
                tags=list(dict.fromkeys([*article.tags, _REDISTRIBUTED_TAG, "care"])),
                language=article.language,
                audience=article.audience,
                category=article.category or "care",
                status="active" if article.status != "restricted" else article.status,
                source_filename=article.source_filename,
                source_checksum=article.source_checksum,
                linked_service_ids=list(article.linked_service_ids),
                linked_branch_ids=list(article.linked_branch_ids),
                notes=_append_notes(article.notes, "Redistributed into Preparation & Aftercare."),
            )
            care_by_id[article.id] = care_article
            derived_ids.append(f"care:{article.id}")

        if classification.notes_home == "branches" and not _notes_already_contain(branches.notes, article):
            branches = BranchesSection(
                items=branches.items,
                notes=_append_notes(branches.notes, block),
            )
            derived_ids.append("branches:notes")

        if classification.notes_home == "handoff" and not _notes_already_contain(handoff.notes, article):
            handoff = HandoffPolicy(
                contacts=handoff.contacts,
                matrix=handoff.matrix,
                notes=_append_notes(handoff.notes, block),
            )
            derived_ids.append("handoff:notes")

        if classification.notes_home == "prices" and not _notes_already_contain(prices.notes, article):
            prices = PricesSection(
                categories=prices.categories,
                catalog=prices.catalog,
                price_entries=prices.price_entries,
                discount_rules=prices.discount_rules,
                dimension_definitions=prices.dimension_definitions,
                resources=prices.resources,
                price_books=prices.price_books,
                rule_sets=prices.rule_sets,
                package_rules=prices.package_rules,
                items=prices.items,
                notes=_append_notes(prices.notes, block),
            )
            derived_ids.append("prices:notes")

        if classification.notes_home == "style":
            if article.source_checksum and article.source_checksum in (style.style_body or ""):
                pass
            else:
                style = StylePolicy(
                    tone=style.tone,
                    formality=style.formality,
                    response_length=style.response_length,
                    emoji_level=style.emoji_level,
                    one_question_at_a_time=style.one_question_at_a_time,
                    use_customer_name=style.use_customer_name,
                    preferred_terms=list(style.preferred_terms),
                    example_replies=list(style.example_replies),
                    do_list=list(style.do_list),
                    dont_list=list(style.dont_list),
                    style_body=_append_notes(style.style_body, block),
                    notes=style.notes,
                )
            derived_ids.append("style:style_body")

        if classification.notes_home == "ai_basics" and classification.ai_basics_field:
            field_name = classification.ai_basics_field
            current = str(getattr(ai, field_name) or "")
            if not _notes_already_contain(current, article):
                setattr(ai, field_name, _append_notes(current, block))
            derived_ids.append(f"ai_basics:{field_name}")

        if classification.dynamic_message_id:
            msg_id = classification.dynamic_message_id
            if msg_id not in dyn_by_id:
                # Store full rule text in EN; owner can localize later — never invent translations.
                dyn_by_id[msg_id] = DynamicMessageRecord(
                    id=msg_id,
                    name=article.title or msg_id,
                    en=article.body,
                    ar="",
                    fr="",
                    notes=(
                        f"Redistributed from knowledge id={article.id} "
                        f"file={article.source_filename or ''} checksum={article.source_checksum or ''}"
                    ),
                )
            derived_ids.append(f"dynamic_messages:{msg_id}")

        linked_services = list(
            dict.fromkeys([*article.linked_service_ids, *[s.id for s in classification.service_derivations]])
        )
        tags = list(dict.fromkeys([*article.tags, _REDISTRIBUTED_TAG, *[f"target:{t}" for t in classification.targets]]))
        if classification.archive_from_knowledge and not classification.keep_in_knowledge_active:
            next_knowledge.append(
                ArticleRecord(
                    id=article.id,
                    title=article.title,
                    body=article.body,
                    tags=tags,
                    language=article.language,
                    audience=article.audience,
                    category=article.category,
                    status="archived",
                    source_filename=article.source_filename,
                    source_checksum=article.source_checksum,
                    linked_service_ids=linked_services,
                    linked_branch_ids=list(article.linked_branch_ids),
                    notes=_append_notes(
                        article.notes,
                        f"Archived after redistribution to: {', '.join(classification.targets)}. Words preserved in destination.",
                    ),
                )
            )
        else:
            next_knowledge.append(
                ArticleRecord(
                    id=article.id,
                    title=article.title,
                    body=article.body,
                    tags=tags,
                    language=article.language,
                    audience=article.audience,
                    category=article.category,
                    status=article.status if article.status != "draft" else "active",
                    source_filename=article.source_filename,
                    source_checksum=article.source_checksum,
                    linked_service_ids=linked_services,
                    linked_branch_ids=list(article.linked_branch_ids),
                    notes=article.notes,
                )
            )

        ledger.append(
            {
                "source_id": article.id,
                "title": article.title,
                "source_filename": article.source_filename,
                "source_checksum": article.source_checksum,
                "targets": list(classification.targets),
                "derived_ids": derived_ids,
                "keep_in_knowledge_active": classification.keep_in_knowledge_active,
                "archive_from_knowledge": classification.archive_from_knowledge,
                "rationale": classification.rationale,
            }
        )

    availability_conflicts = detect_service_availability_conflicts(classifications)

    _put(
        "knowledge",
        KnowledgeSection(items=next_knowledge, notes=knowledge.notes).model_dump(mode="json"),
        tenant_id=tenant_id,
        updated_by=updated_by,
    )
    _put(
        "care",
        CareSection(items=list(care_by_id.values()), notes=care.notes).model_dump(mode="json"),
        tenant_id=tenant_id,
        updated_by=updated_by,
    )
    _put(
        "services",
        ServicesSection(items=list(services_by_id.values()), notes=services.notes).model_dump(mode="json"),
        tenant_id=tenant_id,
        updated_by=updated_by,
    )
    _put("branches", branches.model_dump(mode="json"), tenant_id=tenant_id, updated_by=updated_by)
    _put("handoff", handoff.model_dump(mode="json"), tenant_id=tenant_id, updated_by=updated_by)
    _put("prices", prices.model_dump(mode="json"), tenant_id=tenant_id, updated_by=updated_by)
    _put("style", style.model_dump(mode="json"), tenant_id=tenant_id, updated_by=updated_by)
    _put("ai_basics", ai.model_dump(mode="json"), tenant_id=tenant_id, updated_by=updated_by)
    _put(
        "dynamic_messages",
        DynamicMessagesSection(items=list(dyn_by_id.values()), notes=dyn.notes).model_dump(mode="json"),
        tenant_id=tenant_id,
        updated_by=updated_by,
    )

    out_dir = archive_dir(tenant_id) / "redistribution"
    out_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = out_dir / "mapping_ledger.json"
    report = {
        "tenant_id": tenant_id,
        "mapped": len(ledger),
        "ledger": ledger,
        "availability_conflicts": availability_conflicts,
        "active_knowledge": sum(1 for item in next_knowledge if item.status not in {"archived", "restricted"}),
        "archived_knowledge": sum(1 for item in next_knowledge if item.status == "archived"),
        "services_count": len(services_by_id),
        "care_count": len(care_by_id),
        "checksums": sorted(
            {
                *(row["source_checksum"] for row in ledger if row.get("source_checksum")),
                *(item.source_checksum for item in next_knowledge if item.source_checksum),
                *(item.source_checksum for item in care_by_id.values() if item.source_checksum),
            }
        ),
    }
    ledger_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    report["ledger_path"] = str(ledger_path)
    return report


def section_counts_snapshot(*, tenant_id: str) -> dict[str, Any]:
    """Before/after friendly counts for redistribution reports."""
    counts: dict[str, Any] = {}
    knowledge = KnowledgeSection.model_validate(get_draft("knowledge", tenant_id=tenant_id, create_default=True).payload)
    care = CareSection.model_validate(get_draft("care", tenant_id=tenant_id, create_default=True).payload)
    services = ServicesSection.model_validate(get_draft("services", tenant_id=tenant_id, create_default=True).payload)
    branches = BranchesSection.model_validate(get_draft("branches", tenant_id=tenant_id, create_default=True).payload)
    handoff = HandoffPolicy.model_validate(get_draft("handoff", tenant_id=tenant_id, create_default=True).payload)
    prices = PricesSection.model_validate(get_draft("prices", tenant_id=tenant_id, create_default=True).payload)
    dyn = DynamicMessagesSection.model_validate(
        get_draft("dynamic_messages", tenant_id=tenant_id, create_default=True).payload
    )
    counts["knowledge_active"] = sum(1 for i in knowledge.items if i.status not in {"archived", "restricted"})
    counts["knowledge_archived"] = sum(1 for i in knowledge.items if i.status == "archived")
    counts["knowledge_total"] = len(knowledge.items)
    counts["care"] = len(care.items)
    counts["services"] = len(services.items)
    counts["services_available"] = sum(1 for i in services.items if i.available)
    counts["branches"] = len(branches.items)
    counts["handoff_contacts"] = len(handoff.contacts)
    counts["handoff_notes_chars"] = len(handoff.notes or "")
    counts["prices_notes_chars"] = len(prices.notes or "")
    counts["branches_notes_chars"] = len(branches.notes or "")
    counts["dynamic_messages"] = len(dyn.items)
    counts["price_entries"] = len(prices.price_entries) if isinstance(prices.price_entries, list) else 0
    return counts
