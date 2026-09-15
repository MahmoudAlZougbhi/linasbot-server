"""WAVE G: zero-legacy freeze + KEEP acceptance matrix. CI fails on leftover live mounts."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

GONE = (
    "modules/owner_ai_api.py",
    "modules/owner_ai_v2_api.py",
    "modules/creative_api.py",
    "modules/customer_ai_lab_api.py",
    "services/smart_retrieval_service.py",
    "services/retrieval_debug.py",
    "services/booking",
    "services/api_integrations.py",
    "data/qa_database.json",
    "data/knowledge_files/marwa_extended_tool_rules.json",
    "services/ai_setup/search_metadata/luna_titles.py",
    "services/products/luna_title_resolver.py",
    "dashboard/src/pages/owner/OwnerLab.jsx",
    "modules/mobile_services_api.py",
    "services/service_catalog",
)

DOMAIN = (
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

DRAWER_IDS = (
    "cm",
    "dashboard",
    "smartFollowUp",
    "faq",
    "livechat",
    "requests",
    "integrations",
    "users",
    "subscription",
)

LIVE_PY_ROOTS = ("services", "modules", "handlers", "utils")
SKIP_PARTS = ("/evals/artifacts/", "/__pycache__/", "/node_modules/")


def _live_py() -> list[Path]:
    paths = [ROOT / "main.py", ROOT / "api_config.py", ROOT / "config.py"]
    for folder in LIVE_PY_ROOTS:
        paths.extend((ROOT / folder).rglob("*.py"))
    out: list[Path] = []
    for path in paths:
        text = str(path).replace("\\", "/")
        if any(part in text for part in SKIP_PARTS):
            continue
        out.append(path)
    return out


def _text(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_wave_g_deleted_legacy_paths() -> None:
    missing = [rel for rel in GONE if (ROOT / rel).exists()]
    assert not missing, missing


def test_wave_g_live_mounts_have_no_forbidden_imports() -> None:
    main = _text("main.py")
    assert "modules.owner_ai_api" not in main
    assert "modules.owner_ai_v2_api" not in main
    assert "modules.creative_api" not in main
    assert "modules.customer_ai_lab_api" not in main
    assert "modules.owner_copilot_api" in main
    assert "grouped by product domain" in main
    assert "import modules.web_chat_api" in main
    offenders: list[str] = []
    needles = (
        "from services.booking",
        "import services.booking",
        "services.smart_retrieval_service",
        "modules.owner_ai_api",
        "luna_title_resolver",
        "services.ai_setup.search_metadata.luna_titles",
    )
    for path in _live_py():
        text = path.read_text(encoding="utf-8")
        rel = str(path.relative_to(ROOT))
        for needle in needles:
            if needle in text:
                offenders.append(f"{rel}:{needle}")
    assert not offenders, offenders


def test_wave_g_no_live_test_lab_or_monty_or_linas_fallback() -> None:
    from services.integrations.whatsapp.adapters.whatsapp_factory import WhatsAppFactory
    from services.product_features import is_disabled_api_path

    assert is_disabled_api_path("/api/test") is True
    assert is_disabled_api_path("/api/test-message") is True
    route_hits: list[str] = []
    fallback_hits: list[str] = []
    for path in _live_py():
        text = path.read_text(encoding="utf-8")
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        if rel == "modules/api_security.py" or rel == "services/product_features.py":
            continue
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("@") and "/api/test" in stripped:
                route_hits.append(f"{rel}:{stripped}")
        if 'or "linas"' in text or "or 'linas'" in text:
            fallback_hits.append(rel)
        if 'getenv("LINASBOT_TENANT_ID", "linas")' in text:
            fallback_hits.append(rel)
        if 'getenv("DEFAULT_TENANT_ID", "linas")' in text:
            fallback_hits.append(rel)
    assert not route_hits, route_hits
    assert not fallback_hits, fallback_hits
    constants = _text("services/ai_setup/constants.py")
    assert 'os.getenv("LINASBOT_TENANT_ID", "linas")' not in constants
    assert 'os.getenv("LINASBOT_TENANT_ID", "").strip()' in constants
    try:
        WhatsAppFactory.get_adapter("montymobile")
    except ValueError as exc:
        assert "unsupported" in str(exc).lower()
    else:
        raise AssertionError("Monty must not be a live WhatsApp provider")


def test_wave_g_luna_engine_and_dual_index_gone() -> None:
    publish = _text("services/ai_setup/publish.py")
    policy = _text("services/model_policy.py")
    pricing = _text("services/model_pricing.py")
    llm = _text("services/llm_core_service.py")
    assert "from services.ai_setup.semantic_index import build_index" not in publish
    assert "schedule_tenant_index" in publish
    assert "customer_social_retrieval_voyage" in policy
    assert "customer_social_retrieval_luna" not in policy
    assert "gpt-5.6-luna" not in policy
    assert "gpt-5.6-luna" not in pricing
    assert 'if "luna" in m:' not in llm
    roots = (
        ROOT / "services/ai_setup",
        ROOT / "services/products",
        ROOT / "services/ai_setup/search_metadata",
        ROOT / "services/brain/reply",
        ROOT / "services/model_policy.py",
    )
    offenders: list[str] = []
    for root in roots:
        paths = [root] if root.is_file() else list(root.rglob("*.py"))
        for path in paths:
            if "luna" in path.read_text(encoding="utf-8").lower():
                offenders.append(str(path.relative_to(ROOT)))
    assert not offenders, offenders


def test_wave_g_creative_not_enabled_boc_clinic_gone() -> None:
    from services.billing.membership.plan_catalog import plan_features
    from services.billing.plan_economics import PLAN_FEATURES
    from services.product_features import boc_booking_enabled

    assert boc_booking_enabled() is False
    assert "boc-lb.com" not in _text("api_config.py")
    assert (ROOT / "docs/BOC_NOT_IN_SAAS.md").is_file()
    assert "creative_studio" not in plan_features("pro")
    assert "creative_studio" not in PLAN_FEATURES["pro"]
    assert "creative_studio" not in _text("services/billing/membership/plan_catalog.py")
    assert not (ROOT / "data/qa_database.json").exists()


def test_wave_g_drawer_tiles_and_hub() -> None:
    from services.ai_setup.constants import CM_SECTIONS

    modules = _text("mobile/linas-ai/src/features/nav/drawerModules.ts")
    tree = _text("mobile/linas-ai/src/app/AppScreenTree.tsx")
    hub = _text("mobile/linas-ai/src/features/cm/cmSections.ts")
    for tile in DRAWER_IDS:
        if tile == "cm":
            assert "FEATURED_AI_SETUP" in modules
            assert "id: 'cm'" in modules
        else:
            assert f"id: '{tile}'" in modules
    for name in (
        "CmScreen",
        "DashboardScreen",
        "SmartFollowUpScreen",
        "FaqRoute",
        "LiveChatScreen",
        "RequestsScreen",
        "IntegrationsScreen",
        "UsersScreen",
        "BillingScreen",
        "ChatScreen",
        "NotificationsScreen",
    ):
        assert name in tree
    for tile in ("knowledge", "ai_basics", "branches", "prices", "comments", "requests_appointments"):
        assert tile in hub
    assert "services" not in CM_SECTIONS
    assert "faq" in CM_SECTIONS
    assert "prices" in CM_SECTIONS


def test_wave_g_live_chat_tenant_a_not_b() -> None:
    from types import SimpleNamespace

    from services.access_channels import filter_chats_for_session

    session = SimpleNamespace(tenant_id="tenant-a", role="admin", permissions=None, user_id="op-1")
    payload = {
        "chats": [
            {"conversation_id": "a1", "tenant_id": "tenant-a", "user_id": "whatsapp:1", "channel": "whatsapp"},
            {"conversation_id": "b1", "tenant_id": "tenant-b", "user_id": "whatsapp:2", "channel": "whatsapp"},
        ]
    }
    out = filter_chats_for_session(session, payload)
    assert [row["conversation_id"] for row in out["chats"]] == ["a1"]


def test_wave_g_two_commenters_and_media() -> None:
    from services.brain.history_ids import comment_conversation_id
    from services.brain.media.analyze import analyze_post_media
    from services.brain.media.comment_attach import analysis_fields_for_comment

    alice = comment_conversation_id(
        tenant_id="shop",
        conversation_id="post-thread",
        channel="instagram_comment",
        post_id="p1",
        author_id="ig:alice",
    )
    bob = comment_conversation_id(
        tenant_id="shop",
        conversation_id="post-thread",
        channel="instagram_comment",
        post_id="p1",
        author_id="ig:bob",
    )
    assert alice == "comment:shop:instagram_comment:p1:ig:alice"
    assert bob == "comment:shop:instagram_comment:p1:ig:bob"
    assert alice != bob
    assert comment_conversation_id(tenant_id="shop", channel="instagram_comment", post_id="p1") == ""
    from inspect import getsource

    src = getsource(analysis_fields_for_comment)
    assert "post_media_analysis_status" in src
    assert "analyze_post_media" in src
    assert callable(analyze_post_media)
    assert (ROOT / "services/brain/media/analyze.py").is_file()


def test_wave_g_ai_setup_voyage_requests_integrations_billing() -> None:
    from services.billing.membership.message_flags import message_billing_enabled
    from services.dashboard.message_surface import overlay_message_fields
    from services.iap_product_catalog import credit_product_map, subscription_product_map
    from services.integration_capabilities import list_tenant_integration_status

    publish = _text("services/ai_setup/publish.py")
    pipeline = _text("services/ai_setup/runtime_pipeline.py")
    assert "schedule_tenant_index" in publish
    assert "voyage_search" in pipeline
    assert (ROOT / "modules/requests_api.py").is_file()
    assert (ROOT / "mobile/linas-ai/src/features/requests/RequestsScreen.tsx").is_file()
    rows = list_tenant_integration_status("wave-g")
    platforms = {r["platform"] for r in rows}
    assert "snapchat" not in platforms
    assert {"instagram", "facebook", "tiktok", "web"}.issubset(platforms)
    assert message_billing_enabled() is False
    fields = overlay_message_fields("wave-g", "lite")
    assert fields["message_billing_active"] is False
    assert fields["wallet_unit"] == "credits"
    assert "lite" in subscription_product_map().values()
    assert credit_product_map()["com.linasai.credits.5000"] == 5000
    billing = _text("mobile/linas-ai/src/features/billing/useBillingData.ts")
    assert "/api/entitlements/me" in billing


def test_wave_g_web_marketing_portal_widget() -> None:
    app = _text("dashboard/src/App.jsx")
    shell = _text("dashboard/src/pages/owner/OwnerPortalShell.jsx")
    landing = _text("dashboard/src/pages/public/Landing.jsx")
    public_routes = _text("modules/web_chat_public_routes.py")
    assert 'path="/" element={<Landing />}' in app
    assert 'path="/about"' in app or "path='/about'" in app
    assert "OwnerOverview" in app
    assert "OwnerUsers" in app
    assert "OwnerMessages" in app
    assert "OwnerCatalog" in app
    assert "OwnerCosts" in app
    assert "/owner/lab" not in app
    assert shell.count("{ to: '/owner") == 5
    assert "GuestChatPanel" in landing
    assert "showFab={false}" not in landing
    assert '@app.get("/web-chat/widget.js")' in public_routes


def test_wave_g_copilot_sol_creative_refused() -> None:
    from services.owner_copilot.creative_policy import looks_like_creative_request
    from services.owner_copilot.flags import owner_model_name
    from services.owner_copilot.tool_schemas import tool_names

    assert owner_model_name() == "gpt-5.6-sol"
    assert looks_like_creative_request("create a post please") is True
    assert "create_creative_draft" not in tool_names()
    stream = _text("services/owner_copilot/brain_stream_body.py")
    assert "creative_cancelled" in stream
    assert (ROOT / "modules/owner_copilot_api.py").is_file()
    assert not (ROOT / "modules/owner_ai_api.py").exists()


def test_wave_g_domain_folders_line_cap() -> None:
    oversize: list[str] = []
    for rel in DOMAIN:
        path = ROOT / rel
        assert path.is_dir(), rel
        assert (path / "__init__.py").is_file(), rel
        for py in path.rglob("*.py"):
            text_path = str(py).replace("\\", "/")
            if "/evals/artifacts/" in text_path or "/__pycache__/" in text_path:
                continue
            n = len(py.read_text(encoding="utf-8").splitlines())
            if n > 500:
                oversize.append(f"{py.relative_to(ROOT)}:{n}")
    assert not oversize, oversize
    keep = _text("docs/KEEP_SURFACE.md")
    assert "WAVE G" in keep
    assert "acceptance matrix" in keep.lower()
