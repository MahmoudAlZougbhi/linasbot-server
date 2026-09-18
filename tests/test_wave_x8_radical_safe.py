"""WAVE X8: proven-dead stubs, museum workflows/docs, LINASLASER config, web/mobile crumbs."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_wave_x8_stub_jobs_and_moderation_gone() -> None:
    gone = (
        "modules/meta_social_comment_sync_job.py",
        "modules/tiktok_sync_job.py",
        "services/moderation_service.py",
        "data/knowledge_base.txt",
        "data/style_guide.txt",
        "data/phone_to_room_mapping.json",
    )
    leftover = [rel for rel in gone if (ROOT / rel).exists()]
    assert not leftover, leftover
    assert not (ROOT / "modules/local_qa_api.py").exists()
    assert (ROOT / "services/billing/membership/message_catalog.py").is_file()
    assert (ROOT / "modules/flow_api.py").is_file()


def test_wave_x8_retired_lab_and_founder_workflows_gone() -> None:
    workflows = ROOT / ".github" / "workflows"
    gone = (
        "customer-brain-live-lab-ha.yml",
        "copilot-v2-flags-apply.yml",
        "cm-linas-content-audit.yml",
        "customer-brain-linas-index-ha.yml",
        "prod-brain-linas-smoke.yml",
    )
    leftover = [name for name in gone if (workflows / name).exists()]
    assert not leftover, leftover
    assert not (ROOT / "scripts/prod_apply_copilot_v2_flags.sh").exists()
    # Cutover still calls these founder-named scripts — do not delete.
    assert (ROOT / "scripts/prod_cm_linas_content_audit.sh").is_file()
    assert (ROOT / "scripts/prod_cm_set_linas_bridge_flag.sh").is_file()


def test_wave_x8_config_has_no_linaslaser_bindings() -> None:
    config = (ROOT / "config.py").read_text(encoding="utf-8")
    api_config = (ROOT / "api_config.py").read_text(encoding="utf-8")
    main = (ROOT / "main.py").read_text(encoding="utf-8")
    assert "LINASLASER_" not in config
    assert "LINASLASER_" not in api_config
    assert "EXTERNAL_API_BASE_URL" in config
    assert "TRAINER_WHATSAPP_NUMBER" not in config
    assert "SAVE_KEYWORDS" not in config
    assert "BOOKING_FSM_ENABLED" not in config
    assert "user_booking_state" in config
    assert "user_in_training_mode" in config
    assert "import modules.local_qa_api" not in main
    assert "live-chat-android.apk" not in main
    assert "LIVE_CHAT_ANDROID_APK" not in main


def test_wave_x8_web_and_mobile_crumbs_gone() -> None:
    app = (ROOT / "dashboard/src/App.jsx").read_text(encoding="utf-8")
    portal = app + (ROOT / "dashboard/src/owner_portal/OwnerPortalRoutes.jsx").read_text(encoding="utf-8")
    drawer = (ROOT / "mobile/linas-ai/src/features/nav/drawerModules.ts").read_text(encoding="utf-8")
    auth = (ROOT / "dashboard/src/contexts/AuthContext.jsx").read_text(encoding="utf-8")
    assets = (ROOT / "dashboard/src/constants/landingDesignAssets.js").read_text(encoding="utf-8")
    assert 'path="/"' in app
    assert 'path="/owner"' in portal or 'path="/owner/*"' in portal or "OwnerLayout" in portal
    assert "const register" not in auth
    assert "aiLimits" not in assets
    assert not (ROOT / "dashboard/public/brand/landing/app-screens/screens/12-ai-limits-screen.png").exists()
    ids = [line for line in drawer.splitlines() if "id:" in line and "ControlArea" not in line]
    assert any("dashboard" in line for line in ids)
    assert drawer.count("id: '") + drawer.count('id: "') >= 9
    orphans = (
        "mobile/linas-ai/src/features/dashboard/sections/AlertsCard.tsx",
        "mobile/linas-ai/src/features/billing/PlanCardView.tsx",
        "mobile/linas-ai/src/features/nav/DrawerFooter.tsx",
        "mobile/linas-ai/src/features/cm/editors/BranchesEditor.tsx",
        "mobile/linas-ai/src/hooks/useScreenLoadGate.ts",
        "mobile/linas-ai/src/components/BrandMark.tsx",
    )
    leftover = [rel for rel in orphans if (ROOT / rel).exists()]
    assert not leftover, leftover
    assert (ROOT / "mobile/linas-ai/src/features/cm/editors/PricesEditor.tsx").is_file()
    keep = (ROOT / "docs/KEEP_SURFACE.md").read_text(encoding="utf-8")
    assert "WAVE X8" in keep
