"""Production AI Setup migration helpers (copy-first, no invented facts).

Stages live ``LINASBOT_DATA_ROOT`` content into the fixture-shaped ``legacy/`` tree expected by
:func:`services.cm.migration.migrate_legacy_fixture`, then applies owner-confirmed Lina
structured seeding (branches, laser handoff contacts, preparation guidance) without inventing
prices/hours/phones.

Keyword topic scrub is revoked: recovered Lina files stay active/visible/AI-usable based on
actual content status, not filename/topic keywords.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from services.cm.conflict_validation import validate_restricted_conflicts
from services.cm.constants import DEFAULT_TENANT_ID
from services.cm.migration import migrate_legacy_fixture
from services.cm.schemas import (
    AiBasics,
    ArticleRecord,
    BranchesSection,
    BranchHours,
    BranchRecord,
    CareSection,
    DynamicMessageRecord,
    DynamicMessagesSection,
    GenderAudience,
    HandoffContact,
    HandoffMatrixRow,
    HandoffPolicy,
    LanguagePolicy,
    LocalizedLabels,
    RestrictedPolicy,
    ServiceRecord,
    ServicesSection,
    StylePolicy,
)
from services.cm.scrub_restore import restore_keyword_scrubbed_content
from services.cm.storage import get_draft, put_draft
from services.social_contact_routing import DEFAULT_SOCIAL_WHATSAPP_CONTACTS

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
    (legacy / "style_files").mkdir(parents=True, exist_ok=True)

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

    for sf_root in (
        data_root / "content" / "style_files",
        data_root / "style_files",
        app_data / "style_files",
        app_data / "content" / "style_files",
    ):
        if sf_root.is_dir():
            for path in sorted(sf_root.iterdir()):
                if path.is_file():
                    _copy(path, legacy / "style_files" / path.name)

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
    dyn_src = next((p for p in dyn_candidates if p.exists() and p.is_file() and p.stat().st_size > 0), None)
    if dyn_src is None:
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


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _import_dynamic_messages(*, staging_root: Path, tenant_id: str, updated_by: str) -> dict[str, Any]:
    path = staging_root / "legacy" / "dynamic_messages.json"
    if not path.is_file() or path.stat().st_size == 0:
        return {"imported": 0, "skipped": "missing_or_empty"}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"imported": 0, "skipped": "invalid_json"}

    items: list[DynamicMessageRecord] = []
    if isinstance(raw, dict):
        # Shape A: {"messages": [...]} or {"items": [...]}
        rows = raw.get("items") if isinstance(raw.get("items"), list) else raw.get("messages")
        if isinstance(rows, list):
            source_rows = rows
        else:
            # Shape B: {id: {ar,en,fr,name}} or {id: "text"}
            source_rows = [
                {"id": key, **(value if isinstance(value, dict) else {"en": str(value)})} for key, value in raw.items()
            ]
    elif isinstance(raw, list):
        source_rows = raw
    else:
        return {"imported": 0, "skipped": "unsupported_shape"}

    for row in source_rows:
        if not isinstance(row, dict):
            continue
        msg_id = str(row.get("id") or row.get("key") or row.get("name") or "").strip()
        if not msg_id:
            continue
        items.append(
            DynamicMessageRecord(
                id=msg_id,
                name=str(row.get("name") or row.get("label") or msg_id),
                ar=str(row.get("ar") or row.get("arabic") or ""),
                en=str(row.get("en") or row.get("english") or ""),
                fr=str(row.get("fr") or row.get("french") or ""),
                notes=str(row.get("notes") or "") or None,
            )
        )

    _put_section(
        "dynamic_messages",
        DynamicMessagesSection(items=items, notes="Imported from legacy dynamic_messages.json").model_dump(mode="json"),
        tenant_id=tenant_id,
        updated_by=updated_by,
    )
    return {"imported": len(items)}


def _import_style_files(*, staging_root: Path, tenant_id: str, updated_by: str) -> dict[str, Any]:
    style_path = staging_root / "legacy" / "style_guide.txt"
    style_body = style_path.read_text(encoding="utf-8").strip() if style_path.exists() else ""
    style_files_dir = staging_root / "legacy" / "style_files"
    appended: list[str] = []
    if style_files_dir.is_dir():
        for path in sorted(style_files_dir.iterdir()):
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8", errors="replace").strip()
            if not text:
                continue
            block = f"\n\n--- style_files/{path.name} ---\n{text}"
            style_body = f"{style_body}{block}".strip()
            appended.append(path.name)
    style = StylePolicy(
        style_body=style_body,
        tone="friendly professional",
        formality="warm",
        notes=("Includes style_files: " + ", ".join(appended)) if appended else None,
    )
    _put_section("style", style.model_dump(mode="json"), tenant_id=tenant_id, updated_by=updated_by)
    return {"style_chars": len(style_body), "style_files": appended}


def _import_ai_basics_from_prompt(*, staging_root: Path, tenant_id: str, updated_by: str) -> dict[str, Any]:
    prompt_path = staging_root / "legacy" / "system_prompt_template.txt"
    prompt_text = prompt_path.read_text(encoding="utf-8").strip() if prompt_path.exists() else ""
    settings_path = staging_root / "legacy" / "app_settings.json"
    settings_notes: list[str] = []
    if settings_path.is_file():
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            settings = None
        if isinstance(settings, dict):
            for key in (
                "clinic_name",
                "business_name",
                "assistant_name",
                "default_language",
                "timezone",
                "booking_enabled",
            ):
                if key in settings and settings[key] not in (None, ""):
                    settings_notes.append(f"{key}={settings[key]!r}")

    ai = AiBasics(
        assistant_name="Linas",
        clinic_name="Linas Laser",
        identity_summary="Linas Laser clinic assistant. Answer from published AI Setup facts only.",
        advanced_instructions=prompt_text,
        notes=("app_settings: " + "; ".join(settings_notes)) if settings_notes else None,
    )
    _put_section("ai_basics", ai.model_dump(mode="json"), tenant_id=tenant_id, updated_by=updated_by)
    return {
        "prompt_chars": len(prompt_text),
        "prompt_sha256": _sha256_text(prompt_text) if prompt_text else None,
        "app_settings_keys_noted": len(settings_notes),
    }


def seed_owner_confirmed_structured_truth(*, tenant_id: str, updated_by: str, staging_root: Path) -> dict[str, Any]:
    """Seed structured CM sections from proven contacts + owner-confirmed service truth.

    Does NOT auto-apply INITIAL_RESTRICTED_TOPIC_IDS. Restricted Topics remain an owner-configured
    platform feature only.
    """
    seeded: dict[str, Any] = {}

    # Empty restricted policy on migrate — owner configures Restricted Topics explicitly.
    _put_section(
        "restricted",
        RestrictedPolicy(
            topics=[],
            notes="Restricted Topics are owner-configured. Migration does not auto-restrict recovered Lina files by topic keywords.",
        ).model_dump(mode="json"),
        tenant_id=tenant_id,
        updated_by=updated_by,
    )
    seeded["restricted_topics"] = []

    _put_section(
        "languages",
        LanguagePolicy().model_dump(mode="json"),
        tenant_id=tenant_id,
        updated_by=updated_by,
    )

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

    seeded["style"] = _import_style_files(staging_root=staging_root, tenant_id=tenant_id, updated_by=updated_by)
    seeded["ai_basics"] = _import_ai_basics_from_prompt(
        staging_root=staging_root, tenant_id=tenant_id, updated_by=updated_by
    )
    seeded["dynamic_messages"] = _import_dynamic_messages(
        staging_root=staging_root, tenant_id=tenant_id, updated_by=updated_by
    )

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
            status="active",
        )
    )
    _put_section(
        "care",
        CareSection(items=care_items, notes=care.notes).model_dump(mode="json"),
        tenant_id=tenant_id,
        updated_by=updated_by,
    )
    seeded["care_shave"] = True

    from services.cm.pricing.migration import migrate_staged_price_files_to_catalog

    pricing_import = migrate_staged_price_files_to_catalog(
        staging_root=staging_root,
        tenant_id=tenant_id,
        updated_by=updated_by,
        category_id="body_area",
        category_label="Body areas",
        item_type="body_area",
    )
    seeded["prices_structured"] = int(pricing_import.get("price_entry_count") or 0)
    seeded["pricing_import"] = pricing_import
    seeded["prices_note"] = (
        "Structured catalog/price_entries imported only from proven numeric sources; no invented thresholds or amounts."
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
    """Full production draft migration: stage → fixture migrate → seed → restore scrub."""
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
    restore = restore_keyword_scrubbed_content(tenant_id=tid, updated_by=updated_by)

    from services.cm.redistribution import redistribute_knowledge_draft, section_counts_snapshot

    before_counts = section_counts_snapshot(tenant_id=tid)
    redistribution = redistribute_knowledge_draft(tenant_id=tid, updated_by=updated_by)
    after_counts = section_counts_snapshot(tenant_id=tid)

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
        "scrub": {
            "faq_removed": [],
            "knowledge_archived_ids": [],
            "care_archived_ids": [],
            "disabled": True,
            "reason": "keyword_topic_scrub_revoked",
        },
        "restore": restore,
        "redistribution": redistribution,
        "section_counts_before": before_counts,
        "section_counts_after": after_counts,
        "qa_stats": qa_stats,
        "conflicts": conflicts,
        "conflict_count": len(conflicts),
        "availability_conflicts": redistribution.get("availability_conflicts") or [],
        "publish_ready": len(conflicts) == 0,
    }
