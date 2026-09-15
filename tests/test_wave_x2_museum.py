"""WAVE X2: museum messaging/training/clinic modules stay gone; SFU + template ids stay."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

GONE = (
    "services/smart_messaging.py",
    "services/smart_messaging_catalog.py",
    "services/appointment_scheduler.py",
    "services/daily_template_dispatcher.py",
    "handlers/training_handlers.py",
    "services/training_mode.py",
    "services/qa_database_service.py",
    "services/clinic_holidays_service.py",
    "services/content_files_service.py",
    "modules/content_files_api.py",
    "modules/instructions_api.py",
    "modules/event_handlers_monitor_jobs.py",
    "modules/event_handlers_populate_jobs.py",
    "data/message_templates.json",
    "data/sent_smart_messages.json",
    "data/service_template_mapping.json",
    "data/analytics_daily.json",
)

KEEP = (
    "services/smart_followup/__init__.py",
    "services/live_chat/template_ids.py",
    "services/integrations/whatsapp/cloud_template_service.py",
    "modules/whatsapp_smart_followup_api.py",
)

MUSEUM_MODULES = (
    "services.smart_messaging",
    "services.smart_messaging_catalog",
    "services.appointment_scheduler",
    "services.daily_template_dispatcher",
    "services.qa_database_service",
    "services.clinic_holidays_service",
    "services.content_files_service",
    "services.training_mode",
    "services.training_response_service",
    "handlers.training_handlers",
    "modules.content_files_api",
    "modules.instructions_api",
    "modules.event_handlers_monitor_jobs",
    "modules.event_handlers_populate_jobs",
)

LIVE_PY_ROOTS = ("services", "modules", "utils")
SKIP_PARTS = ("/evals/artifacts/", "/__pycache__/", "/node_modules/")


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


def _imported_modules(path: Path) -> set[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return set()
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_wave_x2_museum_paths_gone() -> None:
    missing_keep = [rel for rel in KEEP if not (ROOT / rel).is_file()]
    leftover = [rel for rel in GONE if (ROOT / rel).exists()]
    assert not missing_keep, missing_keep
    assert not leftover, leftover


def test_wave_x2_live_py_has_no_museum_imports() -> None:
    offenders: list[str] = []
    for path in _live_py():
        imported = _imported_modules(path)
        hits = sorted(
            mod for mod in MUSEUM_MODULES if any(name == mod or name.startswith(f"{mod}.") for name in imported)
        )
        if hits:
            rel = str(path.relative_to(ROOT)).replace("\\", "/")
            offenders.append(f"{rel}: {', '.join(hits)}")
    assert not offenders, offenders


def test_wave_x2_scheduler_keeps_followup_not_clinic_dispatcher() -> None:
    scheduler = (ROOT / "modules/event_handlers_scheduler.py").read_text(encoding="utf-8")
    assert "async def run_smart_followup_worker_job" in scheduler
    assert "run_smart_followup_worker_job" in scheduler
    assert "daily_template_dispatcher" not in scheduler
    assert "monitor_smart_messages" not in scheduler
    main = (ROOT / "main.py").read_text(encoding="utf-8")
    assert "modules.content_files_api" not in main
    assert "modules.instructions_api" not in main
    assert "modules.whatsapp_smart_followup_api" in main
    keep = (ROOT / "docs/KEEP_SURFACE.md").read_text(encoding="utf-8")
    assert "WAVE X2" in keep
