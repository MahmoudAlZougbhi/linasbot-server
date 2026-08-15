"""Meta app registry Postgres backend: authorize, credentials, exclusivity."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event

os.environ["LINAS_WHATSAPP_ALLOW_SQLITE"] = "true"

from db.models import Base  # noqa: E402
from db.session import reset_engine_for_tests, whatsapp_session  # noqa: E402
from services.meta_app_registry import (  # noqa: E402
    APP_A_KEY,
    APP_B_KEY,
    MetaAppRegistry,
    MetaBindingConflictError,
    MetaBindingCredential,
    MetaRegistryError,
    get_meta_app_configs,
    get_meta_registry_readiness,
)
from services.meta_app_registry_pg_store import load_state, state_fingerprint  # noqa: E402
from services.meta_connection_disconnect import disconnect_meta_binding_set  # noqa: E402
from services.mobile_integrations_display import bindings_for_disconnect  # noqa: E402
from tests.meta_app_registry_helpers import _credential  # noqa: E402

pytest_plugins = ("tests.meta_app_registry_fixtures",)

MASTER = "registry-master-secret-used-only-in-tests-123456789"


@pytest.fixture()
def pg_registry(tmp_path: Path, meta_env: None, monkeypatch: pytest.MonkeyPatch) -> MetaAppRegistry:
    url = f"sqlite:///{tmp_path / 'meta_registry.db'}"
    monkeypatch.setenv("LINAS_WHATSAPP_DATABASE_URL", url)
    monkeypatch.setenv("LINAS_WHATSAPP_ALLOW_SQLITE", "true")
    monkeypatch.setenv("META_REGISTRY_BACKEND", "postgres")
    reset_engine_for_tests()
    engine = create_engine(url, future=True)

    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _connection_record):  # type: ignore[no-untyped-def]
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    registry = MetaAppRegistry(
        store_path=tmp_path / "registry.json",
        audit_path=tmp_path / "audit.jsonl",
        master_secret=MASTER,
    )
    yield registry
    reset_engine_for_tests()


def test_postgres_authorize_list_credential_roundtrip(pg_registry: MetaAppRegistry) -> None:
    app_id = get_meta_app_configs()[APP_A_KEY].app_id
    binding = pg_registry.authorize_oauth_asset(
        tenant_id="tenant-pg",
        channel="facebook",
        asset_id="111222333444",
        page_id="111222333444",
        instagram_account_id="",
        app_key=APP_A_KEY,
        credential=_credential(app_id, "111222333444"),
        actor_id="owner-pg",
        page_name="Clinic Page",
    )
    listed = pg_registry.list_bindings(include_inactive=False)
    assert len(listed) == 1
    assert listed[0].binding_id == binding.binding_id
    assert listed[0].page_name == "Clinic Page"
    opened = pg_registry.get_credential(binding)
    assert opened.access_token.startswith("sensitive-token-")
    assert opened.token_profile_id == "111222333444"
    with whatsapp_session(require=True) as session:
        state = load_state(session)
    assert binding.binding_id in state["bindings"]
    assert binding.credential_id in state["credentials"]
    sealed = state["credentials"][binding.credential_id]["sealed"]
    assert sealed.startswith("v1.")
    assert "sensitive-token" not in sealed


def test_postgres_exclusivity_conflict(pg_registry: MetaAppRegistry) -> None:
    configs = get_meta_app_configs()
    pg_registry.authorize_oauth_asset(
        tenant_id="tenant-a",
        channel="facebook",
        asset_id="555666777888",
        page_id="555666777888",
        instagram_account_id="",
        app_key=APP_B_KEY,
        credential=_credential(configs[APP_B_KEY].app_id, "555666777888"),
        actor_id="owner-a",
        status="active",
    )
    with pytest.raises(MetaBindingConflictError, match="already active"):
        pg_registry.authorize_oauth_asset(
            tenant_id="tenant-b",
            channel="facebook",
            asset_id="555666777888",
            page_id="555666777888",
            instagram_account_id="",
            app_key=APP_A_KEY,
            credential=_credential(configs[APP_A_KEY].app_id, "555666777888"),
            actor_id="owner-b",
            status="active",
        )


@pytest.mark.asyncio
async def test_postgres_cross_flow_transition_and_disconnect_settle_every_ig_credential(
    pg_registry: MetaAppRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    instagram_id = "17840000999900001"
    page_id = "445566778899"
    linked = pg_registry.authorize_oauth_asset(
        tenant_id="tenant-a",
        channel="instagram",
        asset_id=instagram_id,
        page_id=page_id,
        instagram_account_id=instagram_id,
        app_key=APP_A_KEY,
        credential=MetaBindingCredential(
            access_token="linked-private-token",
            token_app_id="2963733803971681",
            token_profile_id=page_id,
            scopes=("instagram_basic", "instagram_manage_messages"),
            auth_flow="facebook_login",
        ),
        actor_id="owner",
        auth_flow="facebook_login",
    )
    staged = pg_registry.authorize_oauth_asset(
        tenant_id="tenant-a",
        channel="instagram",
        asset_id=instagram_id,
        page_id="",
        instagram_account_id=instagram_id,
        app_key=APP_A_KEY,
        credential=MetaBindingCredential(
            access_token="direct-private-token",
            token_app_id="1035856539045307",
            token_profile_id=instagram_id,
            scopes=("instagram_business_basic", "instagram_business_manage_messages"),
            auth_flow="instagram_login",
        ),
        actor_id="owner",
        status="testing",
        auth_flow="instagram_login",
        webhook_subscription_status="ready",
        webhook_subscribed_fields=("messages", "messaging_postbacks"),
        create_new_binding=True,
    )
    direct = pg_registry.activate_staged_binding(
        staged.binding_id,
        actor_id="owner",
        expected_generation=staged.generation,
        replace_existing=True,
    )
    pg_registry.archive_superseded_duplicate_bindings(actor_id="owner")

    active = [
        item
        for item in pg_registry.list_bindings(include_inactive=False)
        if item.channel == "instagram" and item.asset_id == instagram_id
    ]
    assert [item.binding_id for item in active] == [direct.binding_id]

    async def settle_without_provider(binding, *, actor_id, registry):  # type: ignore[no-untyped-def]
        changed = registry.set_binding_status(
            binding.binding_id,
            status="disconnected",
            actor_id=actor_id,
            expected_generation=binding.generation,
        )
        return registry.archive_binding_credential(
            changed.binding_id,
            actor_id=actor_id,
            expected_generation=changed.generation,
        )

    monkeypatch.setattr(
        "services.meta_connection_disconnect.disconnect_binding_webhook",
        settle_without_provider,
    )

    @asynccontextmanager
    async def sqlite_transaction_fixture_lock(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        # This fixture exercises the registry's Postgres code through SQLite;
        # durable advisory-lock behavior has its own real-Postgres suite.
        yield

    monkeypatch.setattr(
        "services.meta_connection_disconnect.lock_facebook_page_oauth_operation",
        sqlite_transaction_fixture_lock,
    )
    targets = bindings_for_disconnect(
        "tenant-a",
        "instagram",
        asset_id=instagram_id,
        registry=pg_registry,
    )
    await disconnect_meta_binding_set(
        targets,
        actor_id="owner",
        registry=pg_registry,
        asset_id=instagram_id,
    )

    assert pg_registry.binding_credential_is_available(linked.binding_id) is False
    assert pg_registry.binding_credential_is_available(direct.binding_id) is False
    assert not [
        item
        for item in pg_registry.list_bindings()
        if item.channel == "instagram" and item.asset_id == instagram_id and item.status != "disconnected"
    ]


def test_postgres_backend_fails_closed_without_engine(
    tmp_path: Path, meta_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("META_REGISTRY_BACKEND", "postgres")
    monkeypatch.delenv("LINAS_WHATSAPP_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    reset_engine_for_tests()
    registry = MetaAppRegistry(
        store_path=tmp_path / "registry.json",
        audit_path=tmp_path / "audit.jsonl",
        master_secret=MASTER,
    )
    with pytest.raises(MetaRegistryError, match="unavailable"):
        registry.list_bindings()
    ready, checks = get_meta_registry_readiness(registry)
    assert ready is False
    assert checks["registry_backend_ready"] is False


def test_meta_registry_code_default_is_postgres(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("META_REGISTRY_BACKEND", raising=False)
    from services.meta_app_registry_bindings import resolve_meta_registry_backend

    assert resolve_meta_registry_backend() == "postgres"


def test_dual_write_pg_then_file(tmp_path: Path, meta_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    url = f"sqlite:///{tmp_path / 'meta_dual.db'}"
    monkeypatch.setenv("LINAS_WHATSAPP_DATABASE_URL", url)
    monkeypatch.setenv("LINAS_WHATSAPP_ALLOW_SQLITE", "true")
    monkeypatch.setenv("META_REGISTRY_BACKEND", "dual")
    reset_engine_for_tests()
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    store = tmp_path / "registry.json"
    registry = MetaAppRegistry(
        store_path=store,
        audit_path=tmp_path / "audit.jsonl",
        master_secret=MASTER,
    )
    app_id = get_meta_app_configs()[APP_A_KEY].app_id
    binding = registry.authorize_oauth_asset(
        tenant_id="tenant-dual",
        channel="facebook",
        asset_id="999888777666",
        page_id="999888777666",
        instagram_account_id="",
        app_key=APP_A_KEY,
        credential=_credential(app_id, "999888777666"),
        actor_id="owner-dual",
    )
    assert store.exists()
    with whatsapp_session(require=True) as session:
        pg_fp = state_fingerprint(load_state(session))
    import json

    file_state = json.loads(store.read_text(encoding="utf-8"))
    assert state_fingerprint(file_state) == pg_fp
    assert binding.binding_id in file_state["bindings"]
    reset_engine_for_tests()


def test_import_script_dry_run_and_direct_apply_hard_gate(
    tmp_path: Path, meta_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    import importlib.util

    script = Path(__file__).resolve().parents[1] / "scripts" / "ha" / "import_meta_registry_to_postgres.py"
    spec = importlib.util.spec_from_file_location("import_meta_registry_to_postgres", script)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    url = f"sqlite:///{tmp_path / 'meta_import.db'}"
    monkeypatch.setenv("LINAS_WHATSAPP_DATABASE_URL", url)
    monkeypatch.setenv("LINAS_WHATSAPP_ALLOW_SQLITE", "true")
    monkeypatch.setenv("META_REGISTRY_BACKEND", "file")
    reset_engine_for_tests()
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)

    store = tmp_path / "registry.json"
    file_reg = MetaAppRegistry(
        store_path=store,
        audit_path=tmp_path / "audit.jsonl",
        master_secret=MASTER,
    )
    app_id = get_meta_app_configs()[APP_A_KEY].app_id
    binding = file_reg.authorize_oauth_asset(
        tenant_id="tenant-import",
        channel="facebook",
        asset_id="121314151617",
        page_id="121314151617",
        instagram_account_id="",
        app_key=APP_A_KEY,
        credential=_credential(app_id, "121314151617"),
        actor_id="owner-import",
    )
    monkeypatch.setattr(mod, "_validate_secure_regular_file", lambda path, **_kwargs: path.lstat())
    monkeypatch.setattr(mod, "_require_root", lambda: None)

    # Default is a non-mutating preflight.
    assert mod.main(["--store", str(store)]) == 0
    with whatsapp_session(require=True) as session:
        empty_fp = state_fingerprint(load_state(session))
    assert empty_fp["binding_count"] == 0

    import json

    source_fp = state_fingerprint(json.loads(store.read_text(encoding="utf-8")))
    canonical_env = tmp_path / "canonical.env"
    canonical_env.write_text(
        f"META_REGISTRY_BACKEND=file\nMETA_CREDENTIAL_ENCRYPTION_KEY={MASTER}\nLINAS_WHATSAPP_DATABASE_URL={url}\n",
        encoding="utf-8",
    )
    canonical_env.chmod(0o600)
    from scripts.ha import production_mutation_guard

    monkeypatch.setattr(
        production_mutation_guard,
        "acquire_direct_production_mutation_lock",
        lambda **_kwargs: os.open(tmp_path / "mutation.lock", os.O_RDWR | os.O_CREAT, 0o600),
    )
    apply_args = [
        "--store",
        str(store),
        "--env-file",
        str(canonical_env),
        "--apply",
        "--expected-release-sha",
        "a" * 40,
        "--expected-source-sha256",
        source_fp["state_sha256"],
        "--expected-target-sha256",
        empty_fp["state_sha256"],
    ]
    assert mod.main(apply_args) == 2
    with whatsapp_session(require=True) as session:
        state = load_state(session)
    assert binding.binding_id not in state["bindings"]
    reset_engine_for_tests()
