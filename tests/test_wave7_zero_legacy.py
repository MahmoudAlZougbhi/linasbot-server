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
)

KEEP_PATHS = (
    "docs/KEEP_SURFACE.md",
    "services/live_chat_tenant.py",
    "services/tenant_mobile_dashboard/message_surface.py",
    "services/customer_ai/search/reuse_vectors.py",
    "services/customer_ai/history_ids.py",
    "services/owner_copilot_v2/creative_policy.py",
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
)

PY_ROOTS = ("services", "modules", "handlers", "scripts")
UI_ROOTS = ("dashboard/src", "mobile/linas-ai/src")
GONE_UI_NEEDLES = ("OwnerLab", "OwnerCopilotSetup", "SimpleResourceScreen", "CreativeDraft")
SKIP_NAME_PARTS = ("/evals/artifacts/", "/node_modules/")


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
                if any(frag in name for frag in GONE_IMPORT_FRAGMENTS):
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
    text = (ROOT / "services/live_chat_tenant.py").read_text(encoding="utf-8")
    assert "Fail-closed" in text
    assert "never infer linas" in text.lower() or "Never infer linas" in text


def test_wave2_voyage_reuse_and_wave3_per_author_comments() -> None:
    reuse = (ROOT / "services/customer_ai/search/reuse_vectors.py").read_text(encoding="utf-8")
    history = (ROOT / "services/customer_ai/history_ids.py").read_text(encoding="utf-8")
    assert "content_hash" in reuse
    assert "comment:{tid}:{ch}:{post}:{author}" in history


def test_wave4_billing_sot_and_wave5_web_keep() -> None:
    overlay = (ROOT / "services/tenant_mobile_dashboard/message_surface.py").read_text(encoding="utf-8")
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
    titles = (ROOT / "services/search_metadata/luna_titles.py").read_text(encoding="utf-8")
    hub = (ROOT / "mobile/linas-ai/src/features/cm/cmSections.ts").read_text(encoding="utf-8")
    assert "name: 'resource'" not in nav
    assert "| { name: 'owner' }" in nav
    assert "'owner'" in areas
    assert "CONTROL_ITEMS" not in areas
    assert "montymobile" in factory
    assert "_UNSUPPORTED_LEGACY_PROVIDERS" in factory
    assert "DEAD_LUNA_ENGINE" in titles
    for tile in (
        "knowledge",
        "ai_basics",
        "branches",
        "prices",
        "comments",
        "requests_appointments",
    ):
        assert tile in hub
