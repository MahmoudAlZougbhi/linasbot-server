"""Shared pytest fixtures and deterministic test environment."""

from __future__ import annotations

import asyncio
import os
import tempfile
from collections.abc import Iterator

import pytest

# Deterministic env before any app imports in test modules.
_ROOT = tempfile.mkdtemp(prefix="linas_pytest_")
os.environ.setdefault("LINASBOT_DATA_ROOT", _ROOT)
os.environ.setdefault("LINASLASER_API_BASE_URL", "https://example.com")
os.environ.setdefault("LINASLASER_API_TOKEN", "pytest-token")
os.environ.setdefault("DASHBOARD_AUTH_SECRET", "pytest-dashboard-secret")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-a-real-key")
os.environ.setdefault("ENVIRONMENT", "test")
# Unit tests use file SoT unless a postgres fixture explicitly overrides.
# Production code defaults remain postgres (see services/billing_backend.py).
os.environ.setdefault("LINAS_BILLING_BACKEND", "file")
os.environ.setdefault("LINAS_AUTH_TOKEN_BACKEND", "file")
os.environ.setdefault("META_REGISTRY_BACKEND", "file")
# Hash embeddings are test-harness only (rejected when CM_RUNTIME_MODE=published or
# outside ENVIRONMENT=test). Published-mode tests override to openai + a mocked transport.
os.environ.setdefault("CM_EMBEDDING_PROVIDER", "hash")
os.environ.setdefault("DISABLE_API_DOCS", "true")
os.environ.setdefault("META_WEBHOOK_VERIFY_TOKEN", "pytest-meta-webhook-verify-token-32chars")
os.environ.pop("ALLOW_DEBUG_SIMULATE_WEBHOOK", None)


@pytest.fixture(scope="session")
def event_loop_policy():
    return asyncio.DefaultEventLoopPolicy()


@pytest.fixture(autouse=True)
def _ensure_event_loop():
    """Keep a usable loop for modules that construct asyncio.Lock at import time."""
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())
    yield


pytest_plugins = ("tests.web_chat_acceptance_support",)


@pytest.fixture(scope="session", autouse=True)
def _interrupt_safe_docker_cleanup() -> Iterator[None]:
    from tests.docker_test_containers import (
        cleanup_tracked_containers,
        current_run_owner,
        install_interrupt_safe_cleanup,
        purge_stale_test_containers,
    )

    os.environ.setdefault("LINAS_TEST_RUN_OWNER", current_run_owner())
    install_interrupt_safe_cleanup()
    purge_stale_test_containers()
    yield
    cleanup_tracked_containers()
    purge_stale_test_containers()


@pytest.fixture(autouse=True)
def _default_search_metadata_generator():
    """Tests that Save CM/products without an explicit generator still get valid English metadata.

    Production has no such stub: missing/invalid metadata raises MetadataPreparationError.
    Tests that need failure call reset_metadata_generator() then inject a failing generator.
    """
    from services.search_metadata.generate import SearchMetadata, reset_metadata_generator, set_metadata_generator

    set_metadata_generator(
        lambda _req: SearchMetadata(
            title="English Search Title",
            description="Contains the grounded item content for routing.",
        )
    )
    yield
    reset_metadata_generator()


@pytest.fixture
def enable_faq_plan(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """Active starter plan so CM FAQ write tests pass plan entitlements."""
    import services.entitlements_service as es
    from services.entitlements_service import EntitlementsStore

    store = EntitlementsStore(root=tmp_path / "entitlements")
    real_get = store.get

    def get(tenant_id: str):
        ent = real_get(tenant_id)
        if ent.plan_id != "none" and ent.status != "none":
            return ent
        # set_plan() calls get(); use the real getter to avoid recursion.
        store.get = real_get
        try:
            return store.set_plan(
                tenant_id=tenant_id,
                plan_id="starter",
                status="active",
                source="admin",
            )
        finally:
            store.get = get

    monkeypatch.setattr(store, "get", get)
    monkeypatch.setattr(es, "entitlements_store", store)
    return store
