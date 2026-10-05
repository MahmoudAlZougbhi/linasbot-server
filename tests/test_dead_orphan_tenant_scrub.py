"""Freeze: retired AI orphans stay deleted, and product trees stay tenant-agnostic."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SCAN_ROOTS = (
    "services",
    "modules",
    "utils",
    "storage",
    "scripts",
    "deploy",
    "dashboard/src",
    "mobile/linas-ai/src",
)
SCAN_FILES = (
    "config.py",
    "main.py",
    "requirements.txt",
    ".env.example",
    "nginx-privacy-log.conf",
    "nginx-linasaibot.conf",
    "nginx-api-include.conf",
)
SKIP_PARTS = ("/__pycache__/", "/node_modules/", "/build/")
# Needles live only in this freeze. Product, seeds, and scripts must not.
BRAND_NEEDLES = (
    "linaslaser",
    "lina's laser",
    "lina’s laser",
    "linas laser",
    "lina's bot",
    "linaslaserbot-2.7.22",
    "78847527",
    "70707354",
    "71534928",
    "71226082",
)
RESURRECTED = (
    "SYSTEM_V2",
    "PHASH_PREFIX",
    "SCAN_CAP",
    "modules/owner_ai_api.py",
    "services/brain/planner/openai_plan.py",
    "modules/webhook_handlers_process.py",
)


def _scan_files() -> list[Path]:
    paths = [ROOT / name for name in SCAN_FILES]
    for folder in SCAN_ROOTS:
        base = ROOT / folder
        if not base.exists():
            continue
        paths.extend(path for path in base.rglob("*") if path.is_file())
    out: list[Path] = []
    for path in paths:
        text = str(path).replace("\\", "/")
        if any(part in text for part in SKIP_PARTS):
            continue
        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".pyc", ".woff", ".woff2"}:
            continue
        out.append(path)
    return out


def test_brand_and_founder_strings_stay_out_of_product_and_scripts() -> None:
    hits: list[str] = []
    for path in _scan_files():
        try:
            body = path.read_text(encoding="utf-8", errors="replace").lower()
        except OSError:
            continue
        rel = path.relative_to(ROOT).as_posix()
        for needle in BRAND_NEEDLES:
            if needle in body:
                hits.append(f"{rel}: {needle}")
    assert not hits, hits


def test_retired_ai_paths_do_not_reappear() -> None:
    present = [rel for rel in RESURRECTED if (ROOT / rel).exists()]
    assert not present, present
    loop = (ROOT / "services/brain/agent/loop.py").read_text(encoding="utf-8")
    assert "run_terra_turn" in loop
    assert "run_terra_request_round" not in loop
    assert "identity_greeting_result" not in loop
    webhook = (ROOT / "modules/webhook_handlers.py").read_text(encoding="utf-8")
    assert "process_parsed_message" not in webhook
    assert "whatsapp_inbound_ai_disabled" in webhook
    assert "noqa: F401" not in webhook
