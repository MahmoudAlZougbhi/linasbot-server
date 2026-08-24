from __future__ import annotations

import copy
import importlib.util
import json
import os
from functools import partial
from pathlib import Path

import pytest
from sqlalchemy import create_engine

from db.models import Base
from db.session import reset_engine_for_tests, whatsapp_session
from services.meta_app_registry import APP_A_KEY, MetaAppRegistry, get_meta_app_configs
from services.meta_app_registry_pg_store import (
    load_registry_tables_snapshot,
    load_state,
    registry_tables_fingerprint,
    replace_registry_tables_snapshot,
    save_state,
    state_fingerprint,
)
from tests.meta_app_registry_helpers import _credential

pytest_plugins = ("tests.meta_app_registry_fixtures",)

MASTER = "registry-master-secret-used-only-in-tests-123456789"
SNAPSHOT_RECOVERY = "independent-registry-snapshot-recovery-key-tests-987654321"


def _load_script(name: str):  # type: ignore[no-untyped-def]
    path = Path(__file__).resolve().parents[1] / "scripts" / "ha" / name
    spec = importlib.util.spec_from_file_location(name.removesuffix(".py"), path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def postgres_registry(tmp_path: Path, meta_env: None, monkeypatch: pytest.MonkeyPatch) -> MetaAppRegistry:
    url = f"sqlite:///{tmp_path / 'registry-pg.db'}"
    monkeypatch.setenv("LINAS_WHATSAPP_DATABASE_URL", url)
    monkeypatch.setenv("LINAS_WHATSAPP_ALLOW_SQLITE", "true")
    monkeypatch.setenv("META_REGISTRY_BACKEND", "postgres")
    reset_engine_for_tests()
    Base.metadata.create_all(create_engine(url, future=True))
    registry = MetaAppRegistry(
        store_path=tmp_path / "unused-registry.json",
        audit_path=tmp_path / "unused-audit.jsonl",
        master_secret=MASTER,
    )
    yield registry
    reset_engine_for_tests()


def _seed_one(registry: MetaAppRegistry, *, asset: str = "121314151617") -> None:
    app_id = get_meta_app_configs()[APP_A_KEY].app_id
    registry.authorize_oauth_asset(
        tenant_id="tenant-migration",
        channel="facebook",
        asset_id=asset,
        page_id=asset,
        instagram_account_id="",
        app_key=APP_A_KEY,
        credential=_credential(app_id, asset),
        actor_id="owner-migration",
    )


def test_deep_fingerprint_has_no_ids_and_changes_for_any_persisted_field() -> None:
    state = {
        "schema_version": 1,
        "bindings": {"binding-private-id": {"binding_id": "binding-private-id", "generation": 1}},
        "credentials": {"credential-private-id": {"sealed": "v1.private-ciphertext"}},
        "oauth_states": {"oauth-private-nonce": {"expires_at": 123.0}},
    }
    fingerprint = state_fingerprint(state)
    serialized = json.dumps(fingerprint, sort_keys=True)
    assert "binding-private-id" not in serialized
    assert "credential-private-id" not in serialized
    assert "oauth-private-nonce" not in serialized
    assert "v1.private-ciphertext" not in serialized
    assert fingerprint["binding_count"] == 1
    assert len(fingerprint["state_sha256"]) == 64

    changed = copy.deepcopy(state)
    changed["bindings"]["binding-private-id"]["generation"] = 2
    assert state_fingerprint(changed)["state_sha256"] != fingerprint["state_sha256"]
    changed = copy.deepcopy(state)
    changed["credentials"]["credential-private-id"]["sealed"] = "v1.changed"
    assert state_fingerprint(changed)["state_sha256"] != fingerprint["state_sha256"]


def test_verifier_accepts_only_rigorous_credentialless_disconnected_tombstones() -> None:
    verifier = _load_script("verify_meta_registry_postgres.py")
    tombstone = {
        "binding_id": "binding-private-id",
        "tenant_id": "tenant-private-id",
        "channel": "facebook",
        "asset_id": "asset-private-id",
        "app_key": "linas_first_party",
        "credential_id": "removed-credential-private-id",
        "status": "disconnected",
        "generation": 2,
        "created_at": 10,
        "updated_at": 11,
        "authorized_meta_user_id_hash": "0123456789abcdef",
        "auth_flow": "facebook_login",
    }
    state = {
        "schema_version": 1,
        "bindings": {"binding-private-id": tombstone},
        "credentials": {},
        "oauth_states": {},
    }
    assert verifier.validate_state_invariants(state) == []

    malformed = copy.deepcopy(state)
    malformed["bindings"]["binding-private-id"]["authorized_meta_user_id_hash"] = ""
    assert "binding_credential_missing" in verifier.validate_state_invariants(malformed)

    wrong_status = copy.deepcopy(state)
    wrong_status["bindings"]["binding-private-id"]["status"] = "active"
    assert "binding_credential_missing" in verifier.validate_state_invariants(wrong_status)

    no_lineage = copy.deepcopy(state)
    no_lineage["bindings"]["binding-private-id"]["credential_id"] = ""
    assert "binding_credential_missing" in verifier.validate_state_invariants(no_lineage)

    stray = copy.deepcopy(state)
    stray["credentials"]["stray-private-credential-id"] = {
        "binding_id": "binding-private-id",
        "sealed": "v1.structural-placeholder",
        "aad": "binding-private-id:stray-private-credential-id:1",
    }
    assert "credential_binding_lineage_mismatch" in verifier.validate_state_invariants(stray)


def test_encrypted_snapshot_authenticates_full_payload_without_plaintext(
    meta_env: None,
) -> None:
    snapshot_mod = _load_script("meta_registry_pg_snapshot.py")
    snapshot = {
        "format_version": 1,
        "state": {
            "schema_version": 1,
            "bindings": {"binding-secret-id": {"generation": 7}},
            "credentials": {"credential-secret-id": {"sealed": "v1.secret-ciphertext"}},
            "oauth_states": {"secret-oauth-nonce": {"expires_at": 123.0}},
        },
        "audit_events": [],
    }
    envelope = snapshot_mod.encode_encrypted_snapshot(snapshot, recovery_secret=SNAPSHOT_RECOVERY)
    encoded = json.dumps(envelope, sort_keys=True)
    for forbidden in ("binding-secret-id", "credential-secret-id", "secret-oauth-nonce", "v1.secret-ciphertext"):
        assert forbidden not in encoded
    assert snapshot_mod.decode_encrypted_snapshot(envelope, recovery_secret=SNAPSHOT_RECOVERY) == snapshot
    with pytest.raises(ValueError, match="authentication failed"):
        snapshot_mod.decode_encrypted_snapshot(envelope, recovery_secret=MASTER)

    tampered = copy.deepcopy(envelope)
    raw_ciphertext = bytearray(snapshot_mod._b64decode(tampered["ciphertext"]))
    raw_ciphertext[len(raw_ciphertext) // 2] ^= 0x01
    tampered["ciphertext"] = snapshot_mod._b64encode(bytes(raw_ciphertext))
    with pytest.raises(ValueError, match="authentication failed"):
        snapshot_mod.decode_encrypted_snapshot(tampered, recovery_secret=SNAPSHOT_RECOVERY)

    metadata_tampered = copy.deepcopy(envelope)
    metadata_tampered["created_at"] += 1
    with pytest.raises(ValueError, match="authentication failed"):
        snapshot_mod.decode_encrypted_snapshot(metadata_tampered, recovery_secret=SNAPSHOT_RECOVERY)


def test_four_table_snapshot_restore_is_exact_and_includes_audit(postgres_registry: MetaAppRegistry) -> None:
    _seed_one(postgres_registry)
    with whatsapp_session(require=True) as session:
        before = load_registry_tables_snapshot(session)
        before_fp = registry_tables_fingerprint(before)
    assert before_fp["binding_count"] == 1
    assert before_fp["credential_count"] == 1
    assert before_fp["audit_count"] == 1

    _seed_one(postgres_registry, asset="222333444555")
    with whatsapp_session(require=True) as session:
        changed_fp = registry_tables_fingerprint(load_registry_tables_snapshot(session))
        assert changed_fp != before_fp
        replace_registry_tables_snapshot(session, before)
        session.flush()
        restored_fp = registry_tables_fingerprint(load_registry_tables_snapshot(session))
        assert restored_fp == before_fp

    with whatsapp_session(require=True) as session:
        assert registry_tables_fingerprint(load_registry_tables_snapshot(session)) == before_fp


def test_import_refuses_live_observed_shape_nonempty_pg_vs_stale_nfs(
    tmp_path: Path,
    meta_env: None,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Build the legacy file first (the observed live shape is stale 4/4 vs newer PG 5/5).
    monkeypatch.setenv("META_REGISTRY_BACKEND", "file")
    store = tmp_path / "registry.json"
    file_registry = MetaAppRegistry(store_path=store, audit_path=tmp_path / "audit.jsonl", master_secret=MASTER)
    _seed_one(file_registry)
    stale_state = json.loads(store.read_text(encoding="utf-8"))

    url = f"sqlite:///{tmp_path / 'divergent.db'}"
    monkeypatch.setenv("LINAS_WHATSAPP_DATABASE_URL", url)
    monkeypatch.setenv("LINAS_WHATSAPP_ALLOW_SQLITE", "true")
    monkeypatch.setenv("META_REGISTRY_BACKEND", "postgres")
    reset_engine_for_tests()
    Base.metadata.create_all(create_engine(url, future=True))
    newer_state = copy.deepcopy(stale_state)
    only_binding = next(iter(newer_state["bindings"].values()))
    only_binding["generation"] = int(only_binding["generation"]) + 1
    only_binding["page_name"] = "newer-authoritative-field"
    with whatsapp_session(require=True) as session:
        save_state(session, newer_state)
    before_fp = state_fingerprint(newer_state)

    importer = _load_script("import_meta_registry_to_postgres.py")
    monkeypatch.setattr(importer, "_validate_secure_regular_file", lambda path, **_kwargs: path.lstat())
    assert importer.main(["--store", str(store)]) == 3
    output = capsys.readouterr()
    assert "non-empty and divergent" in output.err
    assert "newer-authoritative-field" not in output.out + output.err

    canonical_env = tmp_path / "canonical.env"
    canonical_env.write_text(
        f"META_REGISTRY_BACKEND=postgres\nMETA_CREDENTIAL_ENCRYPTION_KEY={MASTER}\nLINAS_WHATSAPP_DATABASE_URL={url}\n",
        encoding="utf-8",
    )
    canonical_env.chmod(0o600)
    monkeypatch.setattr(importer, "_require_root", lambda: None)
    from scripts.ha import production_mutation_guard

    monkeypatch.setattr(
        production_mutation_guard,
        "acquire_direct_production_mutation_lock",
        lambda **_kwargs: os.open(tmp_path / "mutation.lock", os.O_RDWR | os.O_CREAT, 0o600),
    )
    source_fp = state_fingerprint(stale_state)
    assert (
        importer.main(
            [
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
                before_fp["state_sha256"],
            ]
        )
        == 2
    )
    with whatsapp_session(require=True) as session:
        assert state_fingerprint(load_state(session)) == before_fp
    reset_engine_for_tests()


def test_readonly_verifier_reports_stale_file_safely(
    tmp_path: Path,
    meta_env: None,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("META_REGISTRY_BACKEND", "file")
    store = tmp_path / "registry.json"
    file_registry = MetaAppRegistry(store_path=store, audit_path=tmp_path / "audit.jsonl", master_secret=MASTER)
    _seed_one(file_registry)
    stale = json.loads(store.read_text(encoding="utf-8"))

    url = f"sqlite:///{tmp_path / 'verify.db'}"
    monkeypatch.setenv("LINAS_WHATSAPP_DATABASE_URL", url)
    monkeypatch.setenv("LINAS_WHATSAPP_ALLOW_SQLITE", "true")
    monkeypatch.setenv("META_REGISTRY_BACKEND", "postgres")
    reset_engine_for_tests()
    Base.metadata.create_all(create_engine(url, future=True))
    newer = copy.deepcopy(stale)
    private_binding_id = next(iter(newer["bindings"]))
    newer["bindings"][private_binding_id]["generation"] += 1
    with whatsapp_session(require=True) as session:
        save_state(session, newer)

    import scripts.ha.import_meta_registry_to_postgres as importer

    monkeypatch.setattr(importer, "_validate_secure_regular_file", lambda path, **_kwargs: path.lstat())
    verifier = _load_script("verify_meta_registry_postgres.py")
    assert verifier.main(["--store", str(store)]) == 0
    output = capsys.readouterr().out
    assert "legacy-file status=stale" in output
    assert private_binding_id not in output
    reset_engine_for_tests()


def test_readonly_verifier_normalizes_legacy_file_defaults_before_parity(
    tmp_path: Path,
    meta_env: None,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("META_REGISTRY_BACKEND", "file")
    store = tmp_path / "registry.json"
    file_registry = MetaAppRegistry(store_path=store, audit_path=tmp_path / "audit.jsonl", master_secret=MASTER)
    _seed_one(file_registry)
    legacy = json.loads(store.read_text(encoding="utf-8"))
    binding = next(iter(legacy["bindings"].values()))
    for field in (
        "auth_flow",
        "previous_binding_id",
        "page_name",
        "instagram_username",
        "authorized_meta_user_id_hash",
        "superseded_by_binding_id",
        "webhook_subscription_status",
        "webhook_subscribed_fields",
        "webhook_subscription_error",
        "webhook_subscription_checked_at",
        "comment_permission_status",
        "comment_permission_verified_at",
        "comment_permission_source",
        "comment_permission_credential_id",
        "comment_permission_token_fingerprint",
    ):
        binding.pop(field, None)
    store.write_text(json.dumps(legacy), encoding="utf-8")

    import scripts.ha.import_meta_registry_to_postgres as importer

    normalized = importer._normalize_file_state_for_postgres(legacy)
    url = f"sqlite:///{tmp_path / 'verify-defaults.db'}"
    monkeypatch.setenv("LINAS_WHATSAPP_DATABASE_URL", url)
    monkeypatch.setenv("LINAS_WHATSAPP_ALLOW_SQLITE", "true")
    monkeypatch.setenv("META_REGISTRY_BACKEND", "postgres")
    reset_engine_for_tests()
    Base.metadata.create_all(create_engine(url, future=True))
    with whatsapp_session(require=True) as session:
        save_state(session, normalized)

    monkeypatch.setattr(importer, "_validate_secure_regular_file", lambda path, **_kwargs: path.lstat())
    verifier = _load_script("verify_meta_registry_postgres.py")
    assert verifier.main(["--store", str(store), "--require-file-parity"]) == 0
    output = capsys.readouterr().out
    assert "legacy-file status=matching" in output
    reset_engine_for_tests()


def test_nfs_retirement_has_no_bypass_or_lazy_unmount_and_requires_exact_proofs() -> None:
    script = (Path(__file__).resolve().parents[1] / "scripts/ha/remove_registry_nfs.sh").read_text()
    assert "--skip-registry-check" not in script
    assert "umount -l" not in script
    assert 'CONFIRMATION_TOKEN="REMOVE_META_REGISTRY_NFS"' in script
    assert "--expected-release-sha" in script
    assert "--expected-pg-sha256" in script
    assert "verify_meta_release_ha.sh" in script
    assert "verify_meta_registry_postgres.py" in script
    assert "local-only" in script
    assert "--env-file" in script
    assert "META_REGISTRY_BACKEND=postgres" in script
    assert 'DATA_ROOT="/opt/linasbot_data"' in script
    assert "registry_nfs_config.py" in script
    assert 'grep -F "$REG_DIR"' not in script
    assert "index($0, reg)" not in script

    snapshot_script = (Path(__file__).resolve().parents[1] / "scripts/ha/meta_registry_pg_snapshot.py").read_text()
    assert "hmac.compare_digest" in snapshot_script
    assert "cross-product rekey procedure" in snapshot_script
    assert "CREDENTIAL_REKEY_RECOVERY_KEY" in snapshot_script
    assert 'add_argument("--recovery-key-file"' in snapshot_script
    runbook = (Path(__file__).resolve().parents[1] / "docs/scale/META_REGISTRY_POSTGRES_HA_CUTOVER.md").read_text()
    assert "whatsapp_credentials.ciphertext" in runbook
    assert "Meta-only rekey is prohibited" in runbook
    assert "--recovery-key-file" in runbook
    assert "pinned per-node Ed25519" in runbook


def test_registry_nfs_config_parser_matches_only_exact_parsed_fields(tmp_path: Path) -> None:
    from scripts.ha.registry_nfs_config import (
        exact_count,
        export_entry_matches,
        filtered_text,
        fstab_entry_matches,
    )

    target = "/opt/linasbot_data/meta_registry"
    source = f"10.106.0.3:{target}"
    fstab_lines = [
        f"{source} {target} nfs4 rw,soft 0 0\n",
        f"{source}_backup {target}_backup nfs4 rw 0 0\n",
        f"# {source} {target} nfs4 rw 0 0\n",
        f"10.106.0.30:{target} {target} nfs4 rw 0 0\n",
        "/dev/vda1 / ext4 defaults 0 1\n",
    ]
    fstab_match = partial(fstab_entry_matches, source=source, target=target)
    assert exact_count(fstab_lines, fstab_match) == 1
    assert filtered_text(fstab_lines, fstab_match) == "".join(fstab_lines[1:])

    export_lines = [
        f"{target} 10.106.0.4(rw,sync)\n",
        f"{target}_backup 10.106.0.4(ro)\n",
        f"# {target} 10.106.0.9(rw)\n",
        "/opt/other 10.106.0.4(ro)\n",
    ]
    export_match = partial(export_entry_matches, target=target)
    assert exact_count(export_lines, export_match) == 1
    assert filtered_text(export_lines, export_match) == "".join(export_lines[1:])


def test_registry_nfs_config_parser_detects_duplicate_exact_fstab_entries() -> None:
    from scripts.ha.registry_nfs_config import exact_count, fstab_entry_matches

    target = "/opt/linasbot_data/meta_registry"
    source = f"10.106.0.3:{target}"
    lines = [f"{source} {target} nfs4 rw 0 0\n"] * 2
    assert exact_count(lines, lambda line: fstab_entry_matches(line, source=source, target=target)) == 2
