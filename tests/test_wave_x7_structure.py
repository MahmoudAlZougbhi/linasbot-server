"""WAVE X7: Meta/Apple/WA templates live under domain packages; no flat meta_*.py."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_wave_x7_flat_meta_and_apple_gone() -> None:
    leftover_meta = sorted((ROOT / "services").glob("meta_*.py"))
    leftover_apple = sorted((ROOT / "services").glob("apple_*.py"))
    leftover_social = sorted((ROOT / "services").glob("social_contact_routing*.py"))
    leftover_wa = sorted((ROOT / "services").glob("whatsapp_cloud_template_service*.py"))
    assert leftover_meta == [], leftover_meta
    assert leftover_apple == [], leftover_apple
    assert leftover_social == [], leftover_social
    assert leftover_wa == [], leftover_wa


def test_wave_x7_domain_packages_present() -> None:
    keep = (
        "services/integrations/meta/__init__.py",
        "services/integrations/meta/meta_oauth.py",
        "services/integrations/meta/meta_app_registry.py",
        "services/billing/apple/__init__.py",
        "services/billing/apple/apple_iap_processor.py",
        "services/billing/apple/apple_sign_in_service.py",
        "services/integrations/whatsapp/cloud_template_service.py",
        "services/integrations/whatsapp/cloud_template_payload.py",
        "services/integrations/social/social_contact_routing.py",
        "services/integrations/social/social_contact_routing_detect.py",
    )
    missing = [rel for rel in keep if not (ROOT / rel).exists()]
    assert not missing, missing
    for rel in keep:
        if rel.endswith(".py") and not rel.endswith("__init__.py"):
            lines = len((ROOT / rel).read_text(encoding="utf-8").splitlines())
            assert lines <= 500, f"{rel} has {lines} lines"


def test_wave_x7_live_imports_use_packages() -> None:
    connections = (ROOT / "modules/meta_connections_api.py").read_text(encoding="utf-8")
    auth_api = (ROOT / "modules/apple_auth_api.py").read_text(encoding="utf-8")
    iap_api = (ROOT / "modules/apple_iap_client_api.py").read_text(encoding="utf-8")
    notify = (ROOT / "services/live_chat/human_takeover_notification_service.py").read_text(encoding="utf-8")
    detect_src = (ROOT / "services/integrations/social/social_contact_routing_detect.py").read_text(encoding="utf-8")
    keep = (ROOT / "docs/KEEP_SURFACE.md").read_text(encoding="utf-8")
    assert "services.integrations.meta.meta_app_registry" in connections
    assert "from services.meta_" not in connections
    assert "services.billing.apple.apple_sign_in_service" in auth_api
    assert "services.billing.apple.apple_iap_processor" in iap_api
    assert "services.integrations.whatsapp.cloud_template_service" in notify
    assert "def is_social_channel" in detect_src
    assert "WAVE X7" in keep
    from services.integrations.social.social_contact_routing_detect import DEFAULT_SOCIAL_WHATSAPP_CONTACTS

    assert DEFAULT_SOCIAL_WHATSAPP_CONTACTS == {}


def test_wave_x7_ha_and_prod_scripts_use_packaged_paths() -> None:
    packaged = "services/integrations/meta/meta_app_registry.py"
    preflight = (ROOT / "scripts/ha/target_platform_readiness_preflight.py").read_text(encoding="utf-8")
    admission = (ROOT / "scripts/ha/live_ready_admission.py").read_text(encoding="utf-8")
    helper = (ROOT / "scripts/ha/deploy_meta_release_ha.sh").read_text(encoding="utf-8")
    assert 'Path("services") / "integrations" / "meta" / "meta_app_registry.py"' in preflight
    assert "REGISTRY_PATH = META_REGISTRY_REL.as_posix()" in admission
    assert f'git_show("{packaged}")' in helper
    hits: list[str] = []
    needles = (
        "from services.meta_",
        "from services.apple_",
        "from services.social_contact_routing import",
        'git_show("services/meta_app_registry.py")',
        '"services" / "meta_app_registry.py"',
        '"services" / "meta_surface_secret_separation.py"',
    )
    for path in (ROOT / "scripts").rglob("*"):
        if not path.is_file() or path.suffix not in {".py", ".sh"}:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for needle in needles:
            if needle in text:
                hits.append(f"{path.relative_to(ROOT)}:{needle}")
    assert hits == [], hits
