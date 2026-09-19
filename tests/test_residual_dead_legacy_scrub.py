"""Residual dead-legacy scrub after #742: islands gone, Terra/silence, no museum imports."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

GONE_DEAD = (
    "services/ai_setup/redistribution.py",
    "services/ai_setup/section_classifier.py",
    "services/ai_setup/pricing/migration_extract.py",
    "services/ai_setup/migration.py",
    "services/ai_setup/prod_migration.py",
    "services/ai_setup/pricing/migration.py",
    "services/ai_setup/scrub_restore.py",
    "services/ai_setup/prod_migration_stage.py",
    "services/ai_setup/embeddings.py",
    "services/ai_setup/pricing/catalog_resolve.py",
    "services/ai_setup/prices_catalog_merge.py",
    "services/scale/isolated_replica_pool.py",
    "services/scale/self_heal.py",
    "services/brain/conversation_router.py",
    "services/brain/conversation_router_patterns.py",
    "services/integrations/meta/meta_comment_rule_dm.py",
    "services/requests/status_ui.py",
    "services/requests/human_detect.py",
)

GONE_LEGACY = (
    "services/brain/greeting.py",
    "services/brain/templates.py",
    "services/brain/inbound/text_handlers_message_greeting.py",
    "services/brain/agent/no_evidence_handoff.py",
    "services/brain/retrieve/expand.py",
    "services/integrations/web_chat/processor_v2_reply.py",
)

KEEP = (
    "services/ai_setup/durable_flags.py",
    "services/brain/greeting_policy.py",
    "services/brain/agent/handoff_policy.py",
    "services/brain/retrieve/hydrate.py",
    "services/integrations/web_chat/processor_reply.py",
    "services/live_chat/service_details.py",
    "services/faq/cm_faq.py",
)

FORBIDDEN_IMPORTS = (
    "from services.ai_setup.redistribution",
    "from services.ai_setup.section_classifier",
    "from services.ai_setup.migration import",
    "from services.ai_setup.prod_migration",
    "from services.ai_setup.embeddings import",
    "from services.ai_setup.pricing.catalog_resolve",
    "from services.ai_setup.pricing.migration import",
    "from services.ai_setup.prices_catalog_merge",
    "from services.ai_setup.scrub_restore",
    "from services.brain.conversation_router",
    "from services.brain.greeting import",
    "from services.brain.templates import",
    "from services.brain.inbound.text_handlers_message_greeting",
    "from services.brain.agent.no_evidence_handoff",
    "from services.brain.retrieve.expand import",
    "from services.integrations.meta.meta_comment_rule_dm",
    "from services.requests.status_ui",
    "from services.requests.human_detect",
    "from services.scale.isolated_replica_pool",
    "from services.scale.self_heal import",
    "from services.integrations.web_chat.processor_v2_reply",
)

FORBIDDEN_SYMBOLS = (
    "safe_greeting_text",
    "GREETING_TEMPLATES",
    "_strip_redundant_greeting_prefix",
    "owner_protocol_text",
    "brain_template(",
)


def _iter_py(*roots: str) -> list[Path]:
    files: list[Path] = []
    for rel in roots:
        root = ROOT / rel
        if root.is_file():
            files.append(root)
        elif root.is_dir():
            files.extend(root.rglob("*.py"))
    return files


def test_dead_and_legacy_paths_are_gone() -> None:
    leftover = [rel for rel in (*GONE_DEAD, *GONE_LEGACY) if (ROOT / rel).exists()]
    assert leftover == []


def test_durable_flags_and_terra_paths_remain() -> None:
    missing = [rel for rel in KEEP if not (ROOT / rel).is_file()]
    assert missing == []


def test_no_production_imports_of_deleted_modules() -> None:
    skip = {str(ROOT / "tests/test_residual_dead_legacy_scrub.py")}
    offenders: list[str] = []
    for path in _iter_py("services", "modules", "scripts"):
        if str(path) in skip:
            continue
        blob = path.read_text(encoding="utf-8")
        for needle in FORBIDDEN_IMPORTS:
            if needle in blob:
                offenders.append(f"{path.relative_to(ROOT)}:{needle}")
    assert not offenders, offenders


def test_no_canned_customer_copy_helpers_in_services() -> None:
    offenders: list[str] = []
    for path in _iter_py("services"):
        blob = path.read_text(encoding="utf-8")
        rel = str(path.relative_to(ROOT))
        for needle in FORBIDDEN_SYMBOLS:
            if needle in blob:
                offenders.append(f"{rel}:{needle}")
    assert not offenders, offenders


def test_live_chat_details_has_no_local_qa_branch() -> None:
    blob = (ROOT / "services/live_chat/service_details.py").read_text(encoding="utf-8")
    assert "local_qa" not in blob
    assert "read_qa_pairs" not in blob
    assert "debug-420609" not in blob
    assert "get_faq_match_context" not in blob
    assert "def get_conversation_details" in blob


def test_faq_owner_verbatim_module_remains() -> None:
    src = (ROOT / "services/brain/faq_exact.py").read_text(encoding="utf-8")
    assert "find_exact_faq" in src
    assert (ROOT / "services/faq/cm_faq.py").is_file()


def test_human_detect_gone_live_human_path_remains() -> None:
    assert not (ROOT / "services/requests/human_detect.py").exists()
    from services.brain.planner.heuristic import plan_message
    from services.requests.constants import PERSISTABLE_REQUEST_TYPES, REQUEST_TYPES
    from services.requests.request_graphs.compiler import destination_from_type

    assert "HUMAN" in REQUEST_TYPES
    assert "HUMAN" not in PERSISTABLE_REQUEST_TYPES
    assert destination_from_type("HUMAN") == "live_chat"
    types = {task.type for task in plan_message("بدي احكي مع حدا").tasks}
    assert "human_request" in types
    types = {task.type for task in plan_message("personal care tips").tasks}
    assert "human_request" not in types


def test_durable_flags_are_quality_gate_and_ha_infrastructure() -> None:
    qg = (ROOT / ".github/workflows/quality-gates.yml").read_text(encoding="utf-8")
    helper = (ROOT / "scripts/ha/deploy_meta_release_ha.sh").read_text(encoding="utf-8")
    preserve = (ROOT / "scripts/prod_cm_preserve_durable_flags.sh").read_text(encoding="utf-8")
    flags = (ROOT / "services/ai_setup/durable_flags.py").read_text(encoding="utf-8")
    assert "services/ai_setup/durable_flags.py" in qg
    assert "prod_cm_preserve_durable_flags.sh" in qg
    assert "prod_cm_preserve_durable_flags.sh" in helper
    assert "from services.ai_setup.durable_flags import" in preserve
    assert "KEEP — deployment / verification infrastructure" in flags
    facts = (ROOT / "services/brain/grounding/facts.py").read_text(encoding="utf-8")
    assert "def _amount_reasons" not in facts
