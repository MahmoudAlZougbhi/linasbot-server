"""WAVE X1: no founder linas special-case; no Laser restricted/WhatsApp defaults; lab off."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

LIVE_PY_ROOTS = ("services", "modules", "utils")
SKIP_REL = {
    "services/team/tenant_registration_service.py",
    "services/team/admin_provisioning_service.py",
}
SKIP_PARTS = ("/evals/artifacts/", "/__pycache__/", "/node_modules/")
_LINAS_EQ = re.compile(
    r'(?:tenant_id|tenant|tid)\s*(?:==|!=)\s*["\']linas["\']'
    r'|["\']linas["\']\s*(?:==|!=)\s*(?:tenant_id|tenant|tid)'
    r'|\.lower\(\)\s*==\s*["\']linas["\']'
)


def _live_py() -> list[Path]:
    paths = [ROOT / "main.py", ROOT / "config.py"]
    for folder in LIVE_PY_ROOTS:
        paths.extend((ROOT / folder).rglob("*.py"))
    out: list[Path] = []
    for path in paths:
        text = str(path).replace("\\", "/")
        if any(part in text for part in SKIP_PARTS):
            continue
        out.append(path)
    return out


def test_wave_x1_restricted_and_whatsapp_defaults_empty() -> None:
    from services.ai_setup.constants import INITIAL_RESTRICTED_LABELS, INITIAL_RESTRICTED_TOPIC_IDS
    from services.integrations.social.social_contact_routing_detect import DEFAULT_SOCIAL_WHATSAPP_CONTACTS

    assert INITIAL_RESTRICTED_TOPIC_IDS == ()
    assert INITIAL_RESTRICTED_LABELS == {}
    assert DEFAULT_SOCIAL_WHATSAPP_CONTACTS == {}


def test_wave_x1_lab_scripts_do_not_write_true() -> None:
    apply_sh = (ROOT / "scripts/prod_apply_customer_brain_flags.sh").read_text(encoding="utf-8")
    stage_sh = (ROOT / "scripts/prod_stage_customer_brain_env.sh").read_text(encoding="utf-8")
    assert '"LINAS_CUSTOMER_AI_LAB": "false"' in apply_sh
    assert '"LINAS_CUSTOMER_AI_LAB": "true"' not in apply_sh
    assert '"LINAS_CUSTOMER_AI_LAB": "false"' in stage_sh
    assert '"LINAS_CUSTOMER_AI_LAB": "true"' not in stage_sh


def test_wave_x1_main_has_no_laser_branding() -> None:
    main = (ROOT / "main.py").read_text(encoding="utf-8")
    assert "Lina's Laser" not in main
    assert "load_training_data" not in main
    assert "Linas AI is ready." in main


def test_wave_x1_live_py_has_no_linas_tenant_equality() -> None:
    offenders: list[str] = []
    for path in _live_py():
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        if rel in SKIP_REL:
            continue
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if _LINAS_EQ.search(line):
                offenders.append(f"{rel}:{i}:{stripped}")
    assert not offenders, offenders


def test_wave_x1_keep_surface_records_wave() -> None:
    keep = (ROOT / "docs/KEEP_SURFACE.md").read_text(encoding="utf-8")
    assert "WAVE X1" in keep
    assert "INITIAL_RESTRICTED" in keep
    assert "LINAS_CUSTOMER_AI_LAB" in keep
    from modules.api_security import is_keep_tenant_api_path

    assert is_keep_tenant_api_path("/api/live-chat/unified-chats") is True
    assert is_keep_tenant_api_path("/api/requests") is True
    assert is_keep_tenant_api_path("/api/settings") is False
