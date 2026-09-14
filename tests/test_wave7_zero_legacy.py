"""WAVE 7: deleted surfaces stay gone; KEEP surfaces stay present."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

GONE_PATHS = (
    "archive",
    "modules/creative_api.py",
    "services/creative_studio_service.py",
    "services/owner_ai_tools_creative.py",
    "services/providers/openai_media.py",
    "services/smart_retrieval_service.py",
    "services/retrieval_debug.py",
    "modules/customer_ai_lab_api.py",
    "dashboard/src/pages/owner/OwnerLab.jsx",
    "dashboard/src/pages/owner/OwnerCopilotSetup.jsx",
    "config/montymobile_templates.json",
    "mobile/linas-ai/src/features/shared/SimpleResourceScreen.tsx",
    "modules/owner_ai_api.py",
    "modules/owner_ai_v2_api.py",
    "services/booking",
    "services/api_integrations.py",
    "data/qa_database.json",
    "data/knowledge_files/marwa_extended_tool_rules.json",
    "services/cm",
    "services/customer_ai",
    "services/owner_copilot_v2",
    "services/owner_ai_orchestrator.py",
    "services/live_chat_tenant.py",
    "services/tenant_mobile_dashboard",
    "services/membership",
    "services/entitlements_service.py",
    "services/search_metadata/luna_titles.py",
    "services/products/luna_title_resolver.py",
    "modules/mobile_services_api.py",
    "services/service_catalog",
)

KEEP_PATHS = (
    "docs/KEEP_SURFACE.md",
    "services/live_chat/tenant.py",
    "services/dashboard/message_surface.py",
    "services/brain/search/reuse_vectors.py",
    "services/search_metadata/title_fields.py",
    "services/brain/history_ids.py",
    "services/owner_copilot/creative_policy.py",
    "services/whatsapp_adapters/whatsapp_factory.py",
    "dashboard/src/pages/owner/OwnerOverview.jsx",
    "dashboard/src/pages/public/Landing.jsx",
    "mobile/linas-ai/src/features/control/OwnerPortalScreen.tsx",
    "mobile/linas-ai/src/features/billing/useBillingData.ts",
)

GONE_IMPORT_FRAGMENTS = (
    "smart_retrieval_service",
    "retrieval_debug",
    "customer_ai_lab_api",
    "owner_ai_tools_creative",
    "creative_studio_service",
    "modules.creative_api",
    "modules.owner_ai_api",
    "modules.owner_ai_v2_api",
    "services.booking",
    "services.api_integrations",
    "services.cm.",
    "services.customer_ai.",
    "services.owner_copilot_v2.",
    "services.owner_ai_orchestrator",
    "services.live_chat_tenant",
    "services.tenant_mobile_dashboard.",
    "services.products.luna_title_resolver",
    "services.search_metadata.luna_titles",
    "modules.mobile_services_api",
    "services.service_catalog",
)

PY_ROOTS = ("services", "modules", "handlers", "scripts")
UI_ROOTS = ("dashboard/src", "mobile/linas-ai/src")
GONE_UI_NEEDLES = ("OwnerLab", "OwnerCopilotSetup", "SimpleResourceScreen", "CreativeDraft")
SKIP_NAME_PARTS = ("/evals/artifacts/", "/node_modules/")

DOMAIN_PACKAGES = (
    "services/ai_setup",
    "services/dashboard",
    "services/smart_followup",
    "services/faq",
    "services/live_chat",
    "services/requests",
    "services/integrations",
    "services/team",
    "services/billing",
    "services/owner_copilot",
    "services/brain",
    "services/brain/comments",
    "services/brain/media",
)


def _import_is_gone(name: str) -> bool:
    for frag in GONE_IMPORT_FRAGMENTS:
        if frag.endswith("."):
            if name == frag[:-1] or name.startswith(frag):
                return True
        elif name == frag or name.startswith(frag + "."):
            return True
    return False


def test_deleted_legacy_paths_are_gone() -> None:
    for rel in GONE_PATHS:
        assert not (ROOT / rel).exists(), rel


def test_keep_surfaces_still_present() -> None:
    for rel in KEEP_PATHS:
        assert (ROOT / rel).is_file(), rel


def test_live_python_does_not_import_deleted_modules() -> None:
    offenders: list[str] = []
    paths = [ROOT / "main.py"]
    for folder in PY_ROOTS:
        paths.extend((ROOT / folder).rglob("*.py"))
    for path in paths:
        text_path = str(path)
        if any(part in text_path.replace("\\", "/") for part in SKIP_NAME_PARTS):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            for name in names:
                if _import_is_gone(name):
                    offenders.append(f"{path.relative_to(ROOT)}:{name}")
    assert not offenders, offenders


def test_web_and_mobile_src_have_no_deleted_ui() -> None:
    offenders: list[str] = []
    for folder in UI_ROOTS:
        for path in (ROOT / folder).rglob("*"):
            if path.suffix not in {".js", ".jsx", ".ts", ".tsx"}:
                continue
            text = path.read_text(encoding="utf-8")
            for needle in GONE_UI_NEEDLES:
                if needle in text:
                    offenders.append(f"{path.relative_to(ROOT)}:{needle}")
    assert not offenders, offenders


def test_wave0_live_chat_is_tenant_fail_closed() -> None:
    text = (ROOT / "services/live_chat/tenant.py").read_text(encoding="utf-8")
    assert "Fail-closed" in text
    assert "never infer linas" in text.lower() or "Never infer linas" in text


def test_wave2_voyage_reuse_and_wave3_per_author_comments() -> None:
    reuse = (ROOT / "services/brain/search/reuse_vectors.py").read_text(encoding="utf-8")
    history = (ROOT / "services/brain/history_ids.py").read_text(encoding="utf-8")
    assert "content_hash" in reuse
    assert "comment:{tid}:{ch}:{post}:{author}" in history


def test_wave4_billing_sot_and_wave5_web_keep() -> None:
    overlay = (ROOT / "services/dashboard/message_surface.py").read_text(encoding="utf-8")
    billing = (ROOT / "mobile/linas-ai/src/features/billing/useBillingData.ts").read_text(encoding="utf-8")
    app = (ROOT / "dashboard/src/App.jsx").read_text(encoding="utf-8")
    landing = (ROOT / "dashboard/src/pages/public/Landing.jsx").read_text(encoding="utf-8")
    public_site = (ROOT / "dashboard/src/constants/publicSite.js").read_text(encoding="utf-8")
    assert "overlay_message_fields" in overlay
    assert "/api/entitlements/me" in billing
    assert "OBSOLETE_OPERATOR_PATHS" in app
    assert "showFab={false}" not in landing
    assert "wallet:" not in public_site


def test_wave6_owner_stays_monty_stays_refused() -> None:
    nav = (ROOT / "mobile/linas-ai/src/app/navigation.ts").read_text(encoding="utf-8")
    areas = (ROOT / "mobile/linas-ai/src/features/control/controlAreas.ts").read_text(encoding="utf-8")
    factory = (ROOT / "services/whatsapp_adapters/whatsapp_factory.py").read_text(encoding="utf-8")
    titles = (ROOT / "services/search_metadata/title_fields.py").read_text(encoding="utf-8")
    hub = (ROOT / "mobile/linas-ai/src/features/cm/cmSections.ts").read_text(encoding="utf-8")
    assert "name: 'resource'" not in nav
    assert "| { name: 'owner' }" in nav
    assert "'owner'" in areas
    assert "CONTROL_ITEMS" not in areas
    assert "montymobile" in factory
    assert "_UNSUPPORTED_LEGACY_PROVIDERS" in factory
    assert "retrieval_title_fields" in titles
    for tile in (
        "knowledge",
        "ai_basics",
        "branches",
        "prices",
        "comments",
        "requests_appointments",
    ):
        assert tile in hub


def test_wave_a_fail_closed_and_deleted_clinic_paths() -> None:
    history = (ROOT / "services/brain/history_ids.py").read_text(encoding="utf-8")
    constants = (ROOT / "services/ai_setup/constants.py").read_text(encoding="utf-8")
    prompt = (ROOT / "utils/utils_prompt.py").read_text(encoding="utf-8")
    main = (ROOT / "main.py").read_text(encoding="utf-8")
    catalog = (ROOT / "services/billing/membership/plan_catalog.py").read_text(encoding="utf-8")
    webhook = (ROOT / "modules/webhook_handlers.py").read_text(encoding="utf-8")
    api_config = (ROOT / "api_config.py").read_text(encoding="utf-8")
    assert "if explicit:" not in history.split("def comment_conversation_id", 1)[1][:400]
    assert 'os.getenv("LINASBOT_TENANT_ID", "linas")' not in constants
    assert "published_mode = True" in prompt
    assert "modules.owner_ai_api" not in main
    assert "modules.owner_copilot_api" in main
    assert "creative_studio" not in catalog
    assert "start_training_mode" not in webhook
    assert "boc-lb.com" not in api_config
    assert (ROOT / "modules/owner_copilot_api.py").is_file()
    assert (ROOT / "docs/BOC_NOT_IN_SAAS.md").is_file()


def test_wave_b_domain_packages_match_drawer() -> None:
    for rel in DOMAIN_PACKAGES:
        assert (ROOT / rel).is_dir(), rel
        assert (ROOT / rel / "__init__.py").is_file(), rel
    main = (ROOT / "main.py").read_text(encoding="utf-8")
    assert "grouped by product domain" in main
    assert "modules.owner_ai_api" not in main
    assert "import modules.owner_copilot_api" in main
    assert not (ROOT / "modules/owner_ai_api.py").exists()
    assert not (ROOT / "modules/owner_ai_v2_api.py").exists()
    assert (ROOT / "modules/owner_copilot_stream_api.py").is_file()
    oversize = []
    skip = ("evals/artifacts", "__pycache__")
    for rel in DOMAIN_PACKAGES:
        for path in (ROOT / rel).rglob("*.py"):
            text_path = str(path).replace("\\", "/")
            if any(part in text_path for part in skip):
                continue
            lines = len(path.read_text(encoding="utf-8").splitlines())
            if lines > 500:
                oversize.append(f"{path.relative_to(ROOT)}:{lines}")
    assert not oversize, oversize


def test_wave_c_voyage_only_and_luna_titles_gone() -> None:
    publish = (ROOT / "services/ai_setup/publish.py").read_text(encoding="utf-8")
    policy = (ROOT / "services/model_policy.py").read_text(encoding="utf-8")
    pipeline = (ROOT / "services/ai_setup/runtime_pipeline.py").read_text(encoding="utf-8")
    assert "from services.ai_setup.semantic_index import build_index" not in publish
    assert "VOYAGE_PROVIDER" in publish or "voyage" in publish.lower()
    assert "customer_social_retrieval_voyage" in policy
    assert "customer_social_retrieval_luna" not in policy
    assert "gpt-5.6-luna" not in policy
    assert "voyage_search" in pipeline
    assert not (ROOT / "services/search_metadata/luna_titles.py").exists()
    assert not (ROOT / "services/products/luna_title_resolver.py").exists()
    assert (ROOT / "services/search_metadata/title_fields.py").is_file()
    assert (ROOT / "services/brain/search/reuse_vectors.py").is_file()
    assert (ROOT / "services/ai_setup/voyage_search.py").is_file()


def test_wave_c_customer_runtime_has_no_luna_engine_names() -> None:
    roots = (
        ROOT / "services/ai_setup",
        ROOT / "services/products",
        ROOT / "services/search_metadata",
        ROOT / "services/customer_reply_v2",
        ROOT / "services/model_policy.py",
    )
    offenders: list[str] = []
    for root in roots:
        paths = [root] if root.is_file() else list(root.rglob("*.py"))
        for path in paths:
            text = path.read_text(encoding="utf-8")
            if "luna" in text.lower():
                offenders.append(str(path.relative_to(ROOT)))
    assert not offenders, offenders


def test_wave_d_one_credit_meter() -> None:
    from services.billing.membership.message_flags import message_billing_cutover, message_billing_enabled
    from services.dashboard.message_surface import overlay_message_fields
    from services.iap_product_catalog import credit_product_map, subscription_product_map
    from services.token_metering import debit_ai_usage

    flags = (ROOT / "services/billing/membership/message_flags.py").read_text(encoding="utf-8")
    metering = (ROOT / "services/token_metering.py").read_text(encoding="utf-8")
    row = (ROOT / "db/models/credit_entitlements.py").read_text(encoding="utf-8")
    catalog = (ROOT / "services/iap_product_catalog.py").read_text(encoding="utf-8")
    assert "Subscription charges credits only" in flags
    assert message_billing_enabled() is False
    assert message_billing_cutover() is False
    assert "token_wallet_service.ensure_ai_allowed" not in metering
    assert "token_wallet_service.debit" not in metering
    assert row.count("pending_plan_id") == 1
    assert row.count("pending_plan_effective_at") == 1
    assert "com.linasai.credits.2500" in catalog
    fields = overlay_message_fields("wave-d", "lite")
    assert fields["message_billing_active"] is False
    assert fields["wallet_unit"] == "credits"
    assert fields["included_credits"] == 7000
    assert fields["available_messages"] is None
    assert debit_ai_usage(tenant_id="wave-d", prompt_tokens=10, completion_tokens=10) is None
    assert "lite" in subscription_product_map().values()
    assert credit_product_map()["com.linasai.credits.5000"] == 5000


def test_wave_e_hub_tiles_and_prices_sot() -> None:
    from services.ai_setup.constants import CM_SECTIONS

    hub = (ROOT / "mobile/linas-ai/src/features/cm/cmSections.ts").read_text(encoding="utf-8")
    cards = (ROOT / "services/brain/retrieve/cards.py").read_text(encoding="utf-8")
    graph = (ROOT / "services/brain/relations/graph.py").read_text(encoding="utf-8")
    pipeline = (ROOT / "services/ai_setup/runtime_pipeline.py").read_text(encoding="utf-8")
    main = (ROOT / "main.py").read_text(encoding="utf-8")
    assert "id: 'services'" not in hub
    for tile in (
        "knowledge",
        "ai_basics",
        "branches",
        "prices",
        "comments",
        "requests_appointments",
    ):
        assert tile in hub
    assert "services" not in CM_SECTIONS
    assert "prices" in CM_SECTIONS
    assert "faq" in CM_SECTIONS
    assert 'legacy = sections.get("services")' not in cards
    assert '_items(sections, "services")' not in graph
    assert 'sections.get("services")' not in pipeline
    assert "mobile_services_api" not in main
    assert not (ROOT / "modules/mobile_services_api.py").exists()
    assert not (ROOT / "services/service_catalog").exists()
    assert not (ROOT / "mobile/linas-ai/src/features/cm/editors/ServicesEditor.tsx").exists()
    keep = (ROOT / "docs/KEEP_SURFACE.md").read_text(encoding="utf-8")
    assert "WAVE E" in keep
    assert "prices.catalog" in keep
