"""Production Content Management migration helpers (copy-first, no invented facts).

Stages live ``LINASBOT_DATA_ROOT`` content into the fixture-shaped ``legacy/`` tree expected by
:func:`services.cm.migration.migrate_legacy_fixture`, then applies owner-confirmed Lina's
business-truth seeding (supported laser service, branches, laser-only handoff, restricted
scrubbing, preparation guidance) without inventing prices/hours/phones.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

from services.cm.conflict_validation import validate_restricted_conflicts
from services.cm.constants import DEFAULT_TENANT_ID, INITIAL_RESTRICTED_TOPIC_IDS
from services.cm.migration import migrate_legacy_fixture
from services.cm.schemas import (
    AiBasics,
    ArticleRecord,
    BranchesSection,
    BranchHours,
    BranchRecord,
    CareSection,
    FaqSection,
    GenderAudience,
    HandoffContact,
    HandoffMatrixRow,
    HandoffPolicy,
    KnowledgeSection,
    LanguagePolicy,
    LocalizedLabels,
    ServiceRecord,
    ServicesSection,
    StylePolicy,
    default_section_payload,
    initial_restricted_policy,
)
from services.cm.storage import get_draft, put_draft
from services.social_contact_routing import DEFAULT_SOCIAL_WHATSAPP_CONTACTS

# Owner-confirmed unsupported services — never offered, priced, or WhatsApp-routed.
UNSUPPORTED_TOPIC_MARKERS: dict[str, tuple[str, ...]] = {
    "tattoo_removal": ("tattoo", "تاتو", "وشم", "détatouage", "detatouage", "tatouage"),
    "co2_laser": ("co2", "co₂", "سي او تو", "سي أو تو"),
    "pigmentation_removal": ("pigmentation", "تصبغ", "تصبغات", "melasma"),
    "facial_skin_cleaning": ("facial", "فيشل", "تنظيف البشرة", "skin cleaning", "skin-cleaning"),
}

SHAVE_CARE_BODY = (
    "Customers are advised to shave at home one day before a laser hair-removal session. "
    "If hair remains at the appointment, staff may use an electric shaver."
)


def resolve_live_data_root(explicit: str | Path | None = None) -> Path:
    if explicit:
        root = Path(explicit)
        if not root.is_dir():
            raise FileNotFoundError(f"Data root not found: {root}")
        return root
    from storage.persistent_storage import get_data_root

    return Path(get_data_root())


def stage_live_data_for_migration(
    *,
    data_root: Path,
    staging_root: Path,
    app_data_root: Path | None = None,
) -> dict[str, Any]:
    """Copy live FAQ/content into ``staging_root/legacy/`` for migrate_legacy_fixture."""
    legacy = staging_root / "legacy"
    if staging_root.exists():
        shutil.rmtree(staging_root)
    legacy.mkdir(parents=True, exist_ok=True)
    (legacy / "knowledge_files").mkdir(parents=True, exist_ok=True)

    copied: list[dict[str, str]] = []
    missing: list[str] = []

    def _copy(src: Path, dest: Path) -> None:
        if not src.exists():
            missing.append(str(src))
            return
        dest.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(src, dest)
        else:
            shutil.copy2(src, dest)
        copied.append({"src": str(src), "dest": str(dest)})

    # Prefer persistent layout; also accept flat project data/ for recovery copies.
    # Production historically keeps FAQ/content under /opt/linasbot/data as well as LINASBOT_DATA_ROOT.
    app_data = Path(app_data_root) if app_data_root is not None else Path("/opt/linasbot/data")
    candidates = {
        "qa_pairs.jsonl": [
            data_root / "qa" / "qa_pairs.jsonl",
            data_root / "qa_pairs.jsonl",
            app_data / "qa" / "qa_pairs.jsonl",
            app_data / "qa_pairs.jsonl",
        ],
        "price_list.txt": [
            data_root / "content" / "price_list.txt",
            data_root / "price_list.txt",
            app_data / "price_list.txt",
            app_data / "content" / "price_list.txt",
        ],
        "knowledge_base.txt": [
            data_root / "content" / "knowledge_base.txt",
            data_root / "knowledge_base.txt",
            app_data / "knowledge_base.txt",
            app_data / "content" / "knowledge_base.txt",
        ],
        "style_guide.txt": [
            data_root / "content" / "style_guide.txt",
            data_root / "style_guide.txt",
            app_data / "style_guide.txt",
            app_data / "content" / "style_guide.txt",
        ],
        "system_prompt_template.txt": [
            data_root / "content" / "system_prompt_template.txt",
            data_root / "system_prompt_template.txt",
            app_data / "system_prompt_template.txt",
            app_data / "content" / "system_prompt_template.txt",
        ],
    }
    for name, paths in candidates.items():
        # Prefer the first *non-empty* existing candidate so an empty placeholder under
        # LINASBOT_DATA_ROOT cannot shadow the live /opt/linasbot/data copy.
        existing = [p for p in paths if p.exists()]
        chosen = next((p for p in existing if p.is_file() and p.stat().st_size > 0), None)
        if chosen is None and existing:
            chosen = existing[0]
        if chosen is None:
            missing.append(name)
            continue
        _copy(chosen, legacy / name)

    for kf_root in (
        data_root / "content" / "knowledge_files",
        data_root / "knowledge_files",
        app_data / "knowledge_files",
        app_data / "content" / "knowledge_files",
    ):
        if kf_root.is_dir():
            for path in sorted(kf_root.glob("*.json")):
                _copy(path, legacy / "knowledge_files" / path.name)

    for pf_root in (
        data_root / "content" / "price_files",
        data_root / "price_files",
        app_data / "price_files",
        app_data / "content" / "price_files",
    ):
        if pf_root.is_dir():
            dest_dir = legacy / "price_files"
            dest_dir.mkdir(parents=True, exist_ok=True)
            for path in sorted(pf_root.glob("*.json")):
                _copy(path, dest_dir / path.name)

    dyn_candidates = [
        data_root / "settings" / "dynamic_messages.json",
        data_root / "dynamic_messages.json",
        app_data / "settings" / "dynamic_messages.json",
        app_data / "dynamic_messages.json",
    ]
    dyn_src = next((p for p in dyn_candidates if p.exists()), None)
    if dyn_src is not None:
        _copy(dyn_src, legacy / "dynamic_messages.json")

    settings_candidates = [
        data_root / "settings" / "app_settings.json",
        data_root / "app_settings.json",
        app_data / "settings" / "app_settings.json",
        app_data / "app_settings.json",
    ]
    settings_src = next((p for p in settings_candidates if p.exists()), None)
    if settings_src is not None:
        _copy(settings_src, legacy / "app_settings.json")

    manifest = {
        "schema": "cm_prod_stage_v1",
        "data_root": str(data_root),
        "app_data_root": str(app_data),
        "copied": copied,
        "missing": missing,
    }
    (staging_root / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return manifest


def _put_section(section: str, payload: dict[str, Any], *, tenant_id: str, updated_by: str) -> None:
    env = get_draft(section, tenant_id=tenant_id, create_default=True)
    put_draft(section, payload=payload, if_match=env.etag, tenant_id=tenant_id, updated_by=updated_by)


def _text_affirms_restricted(text: str) -> str | None:
    lowered = (text or "").lower()
    for topic_id, markers in UNSUPPORTED_TOPIC_MARKERS.items():
        if topic_id not in INITIAL_RESTRICTED_TOPIC_IDS:
            continue
        for marker in markers:
            if marker.lower() in lowered:
                # Affirmation heuristics: offer/provide/price/book language near marker.
                if re.search(
                    r"(offer|provide|available|book|سعر|منقدم|متوفر|نحجز|نوفر|نعمل)",
                    lowered,
                    re.IGNORECASE,
                ):
                    return topic_id
                if topic_id == "tattoo_removal" and re.search(
                    r"(tattoo removal|إزالة التاتو|ازالة التاتو|détatouage)",
                    lowered,
                    re.IGNORECASE,
                ):
                    return topic_id
    return None


def scrub_restricted_affirmations(*, tenant_id: str, updated_by: str) -> dict[str, Any]:
    """Archive FAQ/knowledge items that affirm restricted topics out of the active draft."""
    from datetime import UTC, datetime

    from services.cm.paths import archive_dir, ensure_cm_dirs

    report: dict[str, Any] = {
        "faq_removed": [],
        "knowledge_archived_ids": [],
        "care_archived_ids": [],
        "archive_rel": None,
    }
    ensure_cm_dirs(tenant_id)
    archive_bucket = archive_dir(tenant_id) / "restricted_scrub" / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    archive_bucket.mkdir(parents=True, exist_ok=True)
    report["archive_rel"] = str(archive_bucket)

    faq_env = get_draft("faq", tenant_id=tenant_id, create_default=True)
    faq = FaqSection.model_validate(faq_env.payload)
    kept_faq = []
    removed_faq = []
    for faq_item in faq.items:
        blob = " ".join(f"{v.question} {v.answer}" for v in faq_item.variants)
        topic = _text_affirms_restricted(blob)
        if topic:
            report["faq_removed"].append({"qa_group_id": faq_item.qa_group_id, "topic_id": topic})
            removed_faq.append(faq_item.model_dump(mode="json"))
            continue
        kept_faq.append(faq_item)
    if removed_faq:
        (archive_bucket / "faq_removed.json").write_text(
            json.dumps(removed_faq, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    _put_section(
        "faq",
        FaqSection(items=kept_faq, notes=faq.notes).model_dump(mode="json"),
        tenant_id=tenant_id,
        updated_by=updated_by,
    )

    for section_name, key in (
        ("knowledge", "knowledge_archived_ids"),
        ("care", "care_archived_ids"),
    ):
        env = get_draft(section_name, tenant_id=tenant_id, create_default=True)
        if section_name == "knowledge":
            section_model: KnowledgeSection | CareSection = KnowledgeSection.model_validate(env.payload)
        else:
            section_model = CareSection.model_validate(env.payload)
        kept_articles: list[ArticleRecord] = []
        removed_articles: list[dict[str, Any]] = []
        for article in section_model.items:
            topic = _text_affirms_restricted(f"{article.title}\n{article.body}")
            if topic:
                report[key].append({"id": article.id, "topic_id": topic})
                removed_articles.append(article.model_dump(mode="json"))
                continue
            kept_articles.append(article)
        if removed_articles:
            (archive_bucket / f"{section_name}_removed.json").write_text(
                json.dumps(removed_articles, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
        if section_name == "knowledge":
            payload = KnowledgeSection(items=kept_articles, notes=section_model.notes).model_dump(mode="json")
        else:
            payload = CareSection(items=kept_articles, notes=section_model.notes).model_dump(mode="json")
        _put_section(section_name, payload, tenant_id=tenant_id, updated_by=updated_by)
    return report


def seed_owner_confirmed_structured_truth(*, tenant_id: str, updated_by: str, staging_root: Path) -> dict[str, Any]:
    """Seed structured CM sections from proven contacts + owner-confirmed service truth."""
    seeded: dict[str, Any] = {}

    # Restricted defaults (already in schemas) — force-refresh to owner-confirmed set.
    _put_section(
        "restricted",
        initial_restricted_policy().model_dump(mode="json"),
        tenant_id=tenant_id,
        updated_by=updated_by,
    )
    seeded["restricted_topics"] = list(INITIAL_RESTRICTED_TOPIC_IDS)

    # Languages frozen contract.
    _put_section(
        "languages",
        LanguagePolicy().model_dump(mode="json"),
        tenant_id=tenant_id,
        updated_by=updated_by,
    )

    # Supported service: laser hair removal only (owner-confirmed).
    services = ServicesSection(
        items=[
            ServiceRecord(
                id="laser_hair_removal",
                labels=LocalizedLabels(
                    en="Laser hair removal",
                    ar="إزالة الشعر بالليزر",
                    fr="Épilation laser",
                ),
                available=True,
                category="laser",
                aliases=["laser", "ليزر", "épilation", "hair removal"],
                audience="general",
            )
        ]
    )
    _put_section("services", services.model_dump(mode="json"), tenant_id=tenant_id, updated_by=updated_by)
    seeded["services"] = ["laser_hair_removal"]

    # Branches proven by active social handoff matrix (no invented addresses/hours).
    branches = BranchesSection(
        items=[
            BranchRecord(
                id="beirut",
                labels=LocalizedLabels(en="Beirut (Ramlet El Bayda)", ar="بيروت (الرملة البيضاء)", fr="Beyrouth"),
                address="",
                hours=BranchHours(),
                available=True,
                notes="Address/hours not invented during migration; author from proven production sources.",
            ),
            BranchRecord(
                id="antelias",
                labels=LocalizedLabels(en="Antelias", ar="أنطلياس", fr="Antélias"),
                address="",
                hours=BranchHours(),
                available=True,
                notes="Address/hours not invented during migration; author from proven production sources.",
            ),
        ]
    )
    _put_section("branches", branches.model_dump(mode="json"), tenant_id=tenant_id, updated_by=updated_by)
    seeded["branches"] = ["beirut", "antelias"]

    # Handoff: laser contacts only (tattoo route removed per owner truth).
    contacts: list[HandoffContact] = []
    matrix: list[HandoffMatrixRow] = []
    mapping = {
        "SOCIAL_WHATSAPP_BEIRUT_FEMALE": ("beirut", "female"),
        "SOCIAL_WHATSAPP_BEIRUT_MALE": ("beirut", "male"),
        "SOCIAL_WHATSAPP_ANTELIAS_FEMALE": ("antelias", "female"),
        "SOCIAL_WHATSAPP_ANTELIAS_MALE": ("antelias", "male"),
    }
    for env_name, phone in DEFAULT_SOCIAL_WHATSAPP_CONTACTS.items():
        branch_id, gender_raw = mapping[env_name]
        gender: GenderAudience = "female" if gender_raw == "female" else "male"
        contact_id = env_name.lower()
        contacts.append(
            HandoffContact(
                id=contact_id,
                phone_e164=phone if phone.startswith("+") else f"+{phone}",
                label=env_name,
                gender=gender,
                branch_id=branch_id,
            )
        )
        matrix.append(
            HandoffMatrixRow(
                id=f"row_{contact_id}",
                contact_id=contact_id,
                enabled=True,
                gender=gender,
                branch_id=branch_id,
                topic_id=None,
            )
        )
    handoff = HandoffPolicy(contacts=contacts, matrix=matrix)
    _put_section("handoff", handoff.model_dump(mode="json"), tenant_id=tenant_id, updated_by=updated_by)
    seeded["handoff_contacts"] = [c.id for c in contacts]

    # Style from staged style_guide if present.
    style_path = staging_root / "legacy" / "style_guide.txt"
    style_body = style_path.read_text(encoding="utf-8").strip() if style_path.exists() else ""
    style = StylePolicy(style_body=style_body, tone="friendly professional", formality="warm")
    _put_section("style", style.model_dump(mode="json"), tenant_id=tenant_id, updated_by=updated_by)
    seeded["style_chars"] = len(style_body)

    # AI basics — identity only; advanced instructions get system prompt as narrative archive note.
    prompt_path = staging_root / "legacy" / "system_prompt_template.txt"
    prompt_text = prompt_path.read_text(encoding="utf-8").strip() if prompt_path.exists() else ""
    ai = AiBasics(
        assistant_name="Linas",
        clinic_name="Linas Laser",
        identity_summary="Linas Laser clinic assistant for laser hair removal and related approved information.",
        advanced_instructions=(
            "Answer only from published Content Management facts. "
            "Never invent prices, hours, branches, or WhatsApp numbers. "
            "Never offer tattoo removal, CO2 laser, pigmentation removal, or facial/skin-cleaning."
        ),
        notes=(prompt_text[:4000] if prompt_text else None),
    )
    _put_section("ai_basics", ai.model_dump(mode="json"), tenant_id=tenant_id, updated_by=updated_by)
    seeded["ai_basics"] = True

    # Preparation care article (owner-confirmed).
    care_env = get_draft("care", tenant_id=tenant_id, create_default=True)
    care = CareSection.model_validate(care_env.payload)
    care_items = [item for item in care.items if item.id != "care_shave_before_laser"]
    care_items.append(
        ArticleRecord(
            id="care_shave_before_laser",
            title="Shave before laser hair removal",
            body=SHAVE_CARE_BODY,
            language="en",
            tags=["preparation", "laser_hair_removal", "owner_confirmed"],
        )
    )
    _put_section(
        "care",
        CareSection(items=care_items, notes=care.notes).model_dump(mode="json"),
        tenant_id=tenant_id,
        updated_by=updated_by,
    )
    seeded["care_shave"] = True

    # Prices: do not invent structured amounts. Keep default empty; unstructured price text
    # remains in knowledge from migrate_legacy_fixture with needs_price_structuring tags.
    prices_payload = default_section_payload("prices")
    _put_section("prices", prices_payload, tenant_id=tenant_id, updated_by=updated_by)
    seeded["prices_structured"] = 0
    seeded["prices_note"] = (
        "Structured price rows not invented. Legacy price text preserved in Knowledge for author review."
    )

    return seeded


def run_production_content_migration(
    *,
    data_root: str | Path | None = None,
    staging_root: str | Path,
    tenant_id: str | None = None,
    updated_by: str = "prod_cm_migration",
    app_data_root: str | Path | None = None,
) -> dict[str, Any]:
    """Full production draft migration: stage → fixture migrate → seed truth → scrub conflicts."""
    tid = (tenant_id or DEFAULT_TENANT_ID).strip() or DEFAULT_TENANT_ID
    root = resolve_live_data_root(data_root)
    staging = Path(staging_root)
    stage_report = stage_live_data_for_migration(
        data_root=root,
        staging_root=staging,
        app_data_root=Path(app_data_root) if app_data_root is not None else None,
    )
    migrate_report = migrate_legacy_fixture(source_root=staging, tenant_id=tid, updated_by=updated_by)
    seeded = seed_owner_confirmed_structured_truth(tenant_id=tid, updated_by=updated_by, staging_root=staging)
    scrub = scrub_restricted_affirmations(tenant_id=tid, updated_by=updated_by)

    qa_path = staging / "legacy" / "qa_pairs.jsonl"
    qa_stats: dict[str, Any] = {
        "exists": qa_path.exists(),
        "bytes": 0,
        "lines": 0,
        "parsed_rows": 0,
        "usable_rows": 0,
        "sample_keys": [],
    }
    if qa_path.exists():
        raw = qa_path.read_bytes()
        qa_stats["bytes"] = len(raw)
        lines = [ln for ln in raw.decode("utf-8", errors="replace").splitlines() if ln.strip()]
        qa_stats["lines"] = len(lines)
        for line in lines:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict):
                continue
            qa_stats["parsed_rows"] += 1
            if not qa_stats["sample_keys"]:
                qa_stats["sample_keys"] = sorted(str(k) for k in row.keys())
            if str(row.get("question") or "").strip() and str(row.get("answer") or "").strip():
                qa_stats["usable_rows"] += 1
    drafts = {
        name: dict(get_draft(name, tenant_id=tid, create_default=True).payload)
        for name in ("restricted", "services", "prices", "faq", "knowledge", "handoff")
    }
    conflicts = [
        f.model_dump(mode="json")
        for f in validate_restricted_conflicts(
            restricted=drafts["restricted"],
            services=drafts["services"],
            prices=drafts["prices"],
            faq=drafts["faq"],
            knowledge=drafts["knowledge"],
            handoff=drafts["handoff"],
        )
    ]
    return {
        "tenant_id": tid,
        "data_root": str(root),
        "staging_root": str(staging),
        "stage": stage_report,
        "migrate": migrate_report,
        "seeded": seeded,
        "scrub": scrub,
        "qa_stats": qa_stats,
        "conflicts": conflicts,
        "conflict_count": len(conflicts),
        "publish_ready": len(conflicts) == 0,
    }
