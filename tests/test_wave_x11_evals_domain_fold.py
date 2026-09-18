"""WAVE X11: evals out of runtime; domain packages folded without shims."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_wave_x11_evals_not_runtime_package() -> None:
    assert not (ROOT / "services/brain/evals").exists()
    assert (ROOT / "tests/brain_evals/runner.py").is_file()
    assert (ROOT / "tests/brain_evals/golden_pack.py").is_file()
    runtime_hits: list[str] = []
    for path in (ROOT / "services").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "services.brain.evals" in text or "tests.brain_evals" in text:
            runtime_hits.append(path.relative_to(ROOT).as_posix())
    assert not runtime_hits, runtime_hits
    assert not (ROOT / "services/brain/readiness.py").exists()
    runtime = "\n".join(path.read_text(encoding="utf-8") for path in (ROOT / "services").rglob("*.py"))
    assert "latest_offline_artifact" not in runtime
    pytest_ini = (ROOT / "pytest.ini").read_text(encoding="utf-8")
    assert "norecursedirs" in pytest_ini
    assert "brain_evals" in pytest_ini


def test_wave_x11_domain_folds_no_shims() -> None:
    gone = (
        "services/welcome_pool",
        "services/local_qa_service.py",
        "services/local_qa_service_match.py",
        "services/request_graphs",
        "services/request_drafts",
        "services/search_metadata",
    )
    leftover = [rel for rel in gone if (ROOT / rel).exists()]
    assert not leftover, leftover
    keep = (
        "services/owner_copilot/welcome_pool/__init__.py",
        "services/brain/faq_exact.py",
        "services/faq/faq_cm_invalidation.py",
        "services/requests/request_graphs/service.py",
        "services/requests/request_drafts/engine.py",
        "services/ai_setup/search_metadata/generate.py",
        "services/billing/membership/message_catalog.py",
        "services/brain/inbound/text_handlers.py",
        "scripts/prod_preflight_readonly.sh",
        "pytest.ini",
    )
    missing = [rel for rel in keep if not (ROOT / rel).is_file()]
    assert not missing, missing


def test_wave_x11_keep_drawer_and_portal() -> None:
    app = (ROOT / "dashboard/src/App.jsx").read_text(encoding="utf-8")
    portal = app + (ROOT / "dashboard/src/owner_portal/OwnerPortalRoutes.jsx").read_text(encoding="utf-8")
    drawer = (ROOT / "mobile/linas-ai/src/features/nav/drawerModules.ts").read_text(encoding="utf-8")
    assert 'path="/"' in app
    assert "OwnerLayout" in portal or 'path="/owner"' in portal
    assert drawer.count("id: '") + drawer.count('id: "') >= 9
    from services.ai_setup.search_metadata.generate import SearchMetadata
    from services.brain.faq_exact import find_published_exact_faq
    from services.owner_copilot.welcome_pool import pick_welcome
    from services.requests.request_graphs.service import list_active_graphs

    assert callable(pick_welcome)
    assert callable(find_published_exact_faq)
    assert callable(list_active_graphs)
    assert SearchMetadata is not None
