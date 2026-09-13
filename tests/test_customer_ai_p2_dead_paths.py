"""P2 guards: legacy smart_retrieval stays DEAD for Customer Brain."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest


def test_smart_retrieval_callables_raise_dead() -> None:
    from services import smart_retrieval_service as srs

    assert srs.DEAD_FOR_CUSTOMER_BRAIN is True
    for name in (
        "invalidate_titles_cache",
        "select_relevant_files",
        "get_smart_context",
        "build_retrieval_prompt",
    ):
        with pytest.raises(RuntimeError, match="DEAD"):
            getattr(srs, name)("tenant")


def test_brain_path_does_not_import_luna_retrieval_engine() -> None:
    root = Path(__file__).resolve().parents[1] / "services" / "customer_ai"
    offenders: list[str] = []
    needles = ("gpt-5.6-luna", "resolve_customer_retrieval_policy", "luna_retrieval")
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for needle in needles:
            if needle in text:
                offenders.append(f"{path}:{needle}")
    assert not offenders, f"Customer Brain must not call the old Luna retrieval engine: {offenders}"


def test_brain_retrieve_path_does_not_import_smart_retrieval() -> None:
    root = Path(__file__).resolve().parents[1] / "services" / "customer_ai"
    offenders: list[str] = []
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if "smart_retrieval" in alias.name:
                        offenders.append(f"{path}:{alias.name}")
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                if "smart_retrieval" in mod:
                    offenders.append(f"{path}:{mod}")
    assert not offenders, f"Brain path must not import smart_retrieval: {offenders}"


def test_product_questions_fail_closed_when_stale() -> None:
    from services.customer_ai.search.product_freshness import product_questions_blocked, products_index_stale
    from services.customer_ai.search.store import activate_pointer, mark_pointer_not_ready, reset_memory_store

    reset_memory_store()
    activate_pointer(
        None,
        tenant_id="t-stale",
        space_id="entity",
        source_family="products",
        version="v1",
        count=1,
        source_revision="r1",
    )
    mark_pointer_not_ready(None, tenant_id="t-stale", source_family="products", reason="source_changed")
    assert products_index_stale("t-stale") is True
    blocked = product_questions_blocked("t-stale", {"products"})
    assert blocked is not None
    assert blocked["reason"] == "product_index_stale"
    assert product_questions_blocked("t-stale", {"services"}) is None


@pytest.mark.asyncio
async def test_retrieve_published_fails_closed_on_stale_products(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.customer_ai.retrieve.orchestrate import RetrieveContext, retrieve_published
    from services.customer_ai.search.store import activate_pointer, mark_pointer_not_ready, reset_memory_store

    reset_memory_store()
    activate_pointer(
        None,
        tenant_id="t-prod",
        space_id="entity",
        source_family="products",
        version="v1",
        count=2,
    )
    mark_pointer_not_ready(None, tenant_id="t-prod", source_family="products")

    monkeypatch.setattr(
        "services.customer_ai.retrieve.orchestrate.load_published_content",
        lambda _tid: (_ for _ in ()).throw(RuntimeError("should not load")),
    )
    bundle = await retrieve_published(RetrieveContext(tenant_id="t-prod", query="cream price", families={"products"}))
    assert bundle.outcome == "product_index_stale"
