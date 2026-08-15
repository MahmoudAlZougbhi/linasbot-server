from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from db.models import Base
from db.models.meta_registry import MetaAssetBindingRow, MetaBindingCredentialRow
from db.models.whatsapp_cloud import WhatsAppConnection, WhatsAppCredential
from scripts.ha import rekey_meta_whatsapp_credentials as rekey
from services.meta_app_registry_common import MetaCredentialCipher, MetaCredentialError

OLD_KEY = "old-meta-whatsapp-master-key-for-tests-123456789"
NEW_KEY = "new-meta-whatsapp-master-key-for-tests-987654321"
RECOVERY_KEY = "independent-cross-product-recovery-key-tests-24680"
PROOF_KEY = "independent-transaction-proof-key-for-tests-13579"
TX_ID = "a" * 32
KEY_VERSION = "rotation-20260814"
NODE_SIGNING_KEYS = {node: Ed25519PrivateKey.generate() for node in rekey.REQUIRED_NODES}
NODE_VERIFICATION_KEYS = {node: key.public_key() for node, key in NODE_SIGNING_KEYS.items()}
HOST_IDENTITIES = {
    node: {
        **rekey.FIXED_NODE_IDENTITIES[node],
        "machine_id_sha256": character * 64,
    }
    for node, character in zip(rekey.REQUIRED_NODES, ("1", "2"), strict=True)
}


def _guard_sha(node_id: str) -> str:
    return hashlib.sha256(
        rekey._guard_payload(
            node_id=node_id,
            transaction_id=TX_ID,
            proof_secret=PROOF_KEY,
            host_identity=HOST_IDENTITIES[node_id],
        )
    ).hexdigest()


def _provision_static_guard(systemd_root: Path, marker: Path) -> dict[str, Path]:
    payload = rekey._guard_dropin_payload(marker)
    paths = rekey._guard_dropin_paths(systemd_root)
    for path in paths.values():
        path.parent.mkdir(mode=0o755, exist_ok=True)
        path.write_bytes(payload)
        path.chmod(0o644)
    return paths


@pytest.fixture()
def credential_db(tmp_path: Path) -> tuple[Session, Path]:
    engine = create_engine(f"sqlite:///{tmp_path / 'credential.db'}", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = factory()
    old_cipher = MetaCredentialCipher(OLD_KEY)

    binding_id = "binding-private-test-id"
    credential_id = "meta-credential-private-test-id"
    aad = f"{binding_id}:{credential_id}:facebook"
    session.add(
        MetaAssetBindingRow(
            binding_id=binding_id,
            tenant_id="tenant-private-test",
            channel="facebook",
            asset_id="page-private-test",
            page_id="page-private-test",
            instagram_account_id="",
            app_key="linas_first_party",
            credential_id=credential_id,
            status="active",
            generation=7,
            created_at=10,
            updated_at=20,
        )
    )
    session.flush()
    session.add(
        MetaBindingCredentialRow(
            credential_id=credential_id,
            binding_id=binding_id,
            aad=aad,
            sealed=old_cipher.seal(
                {"access_token": "meta-private-token", "scopes": ["pages_messaging"]},
                aad=aad,
            ),
            created_at=10,
        )
    )

    connection_id = "wa-connection-private-test-id"
    wa_credential_id = "wa-credential-private-test-id"
    wa_aad = f"whatsapp:tenant-private-test:{connection_id}"
    connection = WhatsAppConnection(
        id=connection_id,
        tenant_id="tenant-private-test",
        created_by_user_id="owner-private-test",
        meta_app_key="linas_first_party",
        meta_app_id="2963733803971681",
        waba_id="waba-private-test",
        phone_number_id="phone-private-test",
        lifecycle_status="connected",
        credential_id=wa_credential_id,
        credential_generation=3,
    )
    session.add(connection)
    session.flush()
    session.add(
        WhatsAppCredential(
            id=wa_credential_id,
            tenant_id="tenant-private-test",
            connection_id=connection_id,
            generation=3,
            ciphertext=old_cipher.seal(
                {
                    "access_token": "whatsapp-private-token",
                    "channel": "whatsapp",
                    "scopes": ["whatsapp_business_messaging"],
                },
                aad=wa_aad,
            ),
            encryption_key_version="v1",
            token_type="user",
            scopes=["whatsapp_business_messaging"],
        )
    )
    session.commit()
    yield session, tmp_path
    session.close()
    engine.dispose()


def _fingerprint(session: Session) -> dict[str, object]:
    return rekey._fingerprint_snapshot(rekey._snapshot(rekey.load_inventory(session)))


def _assert_decrypts_with(session: Session, secret: str) -> None:
    rekey._validate_inventory_decryption(rekey.load_inventory(session), secret)


def test_meta_and_whatsapp_rekey_and_rollback_are_cross_product_atomic(
    credential_db: tuple[Session, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    session, tmp_path = credential_db
    monkeypatch.setattr(rekey, "_acquire_database_locks", lambda *_args, **_kwargs: None)
    before = _fingerprint(session)
    preimage_path = tmp_path / "preimage.enc"

    before_fp, after_fp = rekey.apply_rekey_transaction(
        session,
        old_secret=OLD_KEY,
        new_secret=NEW_KEY,
        new_key_version="rotation-20260814",
        expected_current_sha256=str(before["full_sha256"]),
        preimage_path=preimage_path,
        recovery_secret=RECOVERY_KEY,
    )
    session.commit()

    assert before_fp == before
    assert after_fp["full_sha256"] != before_fp["full_sha256"]
    assert after_fp["structural_sha256"] == before_fp["structural_sha256"]
    _assert_decrypts_with(session, NEW_KEY)
    with pytest.raises(MetaCredentialError):
        _assert_decrypts_with(session, OLD_KEY)
    wa_row = session.scalar(select(WhatsAppCredential))
    assert wa_row is not None and wa_row.encryption_key_version == "rotation-20260814"

    restored_source = rekey.read_preimage(preimage_path, recovery_secret=RECOVERY_KEY)
    current = _fingerprint(session)
    _, restored_fp = rekey.restore_preimage_transaction(
        session,
        current_secret=NEW_KEY,
        restored_secret=OLD_KEY,
        expected_current_sha256=str(current["full_sha256"]),
        preimage=restored_source,
        pre_rollback_path=tmp_path / "pre-rollback.enc",
        recovery_secret=RECOVERY_KEY,
    )
    session.commit()
    assert restored_fp == before_fp
    _assert_decrypts_with(session, OLD_KEY)
    with pytest.raises(MetaCredentialError):
        _assert_decrypts_with(session, NEW_KEY)


@pytest.mark.parametrize("fail_after", [1, 2])
def test_rekey_failure_rolls_back_meta_and_whatsapp_together(
    credential_db: tuple[Session, Path],
    monkeypatch: pytest.MonkeyPatch,
    fail_after: int,
) -> None:
    session, tmp_path = credential_db
    monkeypatch.setattr(rekey, "_acquire_database_locks", lambda *_args, **_kwargs: None)
    before = _fingerprint(session)
    with pytest.raises(RuntimeError, match="injected rekey failure"):
        rekey.apply_rekey_transaction(
            session,
            old_secret=OLD_KEY,
            new_secret=NEW_KEY,
            new_key_version="rotation-20260814",
            expected_current_sha256=str(before["full_sha256"]),
            preimage_path=tmp_path / f"failure-{fail_after}.enc",
            recovery_secret=RECOVERY_KEY,
            fail_after_updates=fail_after,
        )
    session.rollback()
    assert _fingerprint(session) == before
    _assert_decrypts_with(session, OLD_KEY)


def test_rollback_failure_leaves_both_products_on_new_key(
    credential_db: tuple[Session, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    session, tmp_path = credential_db
    monkeypatch.setattr(rekey, "_acquire_database_locks", lambda *_args, **_kwargs: None)
    original = _fingerprint(session)
    preimage_path = tmp_path / "rollback-source.enc"
    rekey.apply_rekey_transaction(
        session,
        old_secret=OLD_KEY,
        new_secret=NEW_KEY,
        new_key_version="rotation-20260814",
        expected_current_sha256=str(original["full_sha256"]),
        preimage_path=preimage_path,
        recovery_secret=RECOVERY_KEY,
    )
    session.commit()
    rekeyed = _fingerprint(session)
    preimage = rekey.read_preimage(preimage_path, recovery_secret=RECOVERY_KEY)

    with pytest.raises(RuntimeError, match="injected rollback failure"):
        rekey.restore_preimage_transaction(
            session,
            current_secret=NEW_KEY,
            restored_secret=OLD_KEY,
            expected_current_sha256=str(rekeyed["full_sha256"]),
            preimage=preimage,
            pre_rollback_path=tmp_path / "rollback-failure-backup.enc",
            recovery_secret=RECOVERY_KEY,
            fail_after_updates=1,
        )
    session.rollback()
    assert _fingerprint(session) == rekeyed
    _assert_decrypts_with(session, NEW_KEY)
    with pytest.raises(MetaCredentialError):
        _assert_decrypts_with(session, OLD_KEY)


def test_rollback_refuses_to_overwrite_post_rekey_plaintext_change(
    credential_db: tuple[Session, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    session, tmp_path = credential_db
    monkeypatch.setattr(rekey, "_acquire_database_locks", lambda *_args, **_kwargs: None)
    original = _fingerprint(session)
    preimage_path = tmp_path / "semantic-rollback-source.enc"
    rekey.apply_rekey_transaction(
        session,
        old_secret=OLD_KEY,
        new_secret=NEW_KEY,
        new_key_version=KEY_VERSION,
        expected_current_sha256=str(original["full_sha256"]),
        preimage_path=preimage_path,
        recovery_secret=RECOVERY_KEY,
    )
    session.commit()

    credential = session.scalar(select(MetaBindingCredentialRow))
    assert credential is not None
    cipher = MetaCredentialCipher(NEW_KEY)
    changed_payload = cipher.open(credential.sealed, aad=credential.aad)
    changed_payload["access_token"] = "post-rekey-private-change"
    credential.sealed = cipher.seal(changed_payload, aad=credential.aad)
    session.commit()
    changed = _fingerprint(session)
    pre_rollback = tmp_path / "must-not-back-up-changed-state.enc"

    with pytest.raises(RuntimeError, match="overwrite changed credential plaintext"):
        rekey.restore_preimage_transaction(
            session,
            current_secret=NEW_KEY,
            restored_secret=OLD_KEY,
            expected_current_sha256=str(changed["full_sha256"]),
            preimage=rekey.read_preimage(preimage_path, recovery_secret=RECOVERY_KEY),
            pre_rollback_path=pre_rollback,
            recovery_secret=RECOVERY_KEY,
        )
    session.rollback()
    assert _fingerprint(session) == changed
    assert not pre_rollback.exists()


def test_tampered_credential_aborts_before_any_write_or_backup(
    credential_db: tuple[Session, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    session, tmp_path = credential_db
    monkeypatch.setattr(rekey, "_acquire_database_locks", lambda *_args, **_kwargs: None)
    row = session.scalar(select(WhatsAppCredential))
    assert row is not None
    row.ciphertext = row.ciphertext[:-2] + "AA"
    session.commit()
    before = _fingerprint(session)
    backup = tmp_path / "must-not-exist.enc"
    with pytest.raises(MetaCredentialError):
        rekey.apply_rekey_transaction(
            session,
            old_secret=OLD_KEY,
            new_secret=NEW_KEY,
            new_key_version="rotation-20260814",
            expected_current_sha256=str(before["full_sha256"]),
            preimage_path=backup,
            recovery_secret=RECOVERY_KEY,
        )
    session.rollback()
    assert not backup.exists()
    assert _fingerprint(session) == before


def test_preimage_uses_independent_recovery_key_and_authenticates_every_byte(
    credential_db: tuple[Session, Path],
) -> None:
    session, _ = credential_db
    snapshot = rekey._snapshot(rekey.load_inventory(session))
    envelope = rekey.encode_preimage(snapshot, recovery_secret=RECOVERY_KEY)
    serialized = json.dumps(envelope, sort_keys=True)
    for forbidden in (
        "meta-private-token",
        "whatsapp-private-token",
        "meta-credential-private-test-id",
        "wa-credential-private-test-id",
    ):
        assert forbidden not in serialized
    assert rekey.decode_preimage(envelope, recovery_secret=RECOVERY_KEY) == snapshot
    with pytest.raises(ValueError, match="authentication failed"):
        rekey.decode_preimage(envelope, recovery_secret=OLD_KEY)

    tampered = copy.deepcopy(envelope)
    raw = bytearray(rekey._b64decode(str(tampered["ciphertext"])))
    raw[len(raw) // 2] ^= 0x01
    tampered["ciphertext"] = rekey._b64encode(bytes(raw))
    with pytest.raises(ValueError, match="authentication failed"):
        rekey.decode_preimage(tampered, recovery_secret=RECOVERY_KEY)


def test_recovery_key_must_differ_from_both_runtime_keys(
    credential_db: tuple[Session, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    session, tmp_path = credential_db
    monkeypatch.setattr(rekey, "_acquire_database_locks", lambda *_args, **_kwargs: None)
    before = _fingerprint(session)
    with pytest.raises(ValueError, match="independent"):
        rekey.apply_rekey_transaction(
            session,
            old_secret=OLD_KEY,
            new_secret=NEW_KEY,
            new_key_version="rotation-20260814",
            expected_current_sha256=str(before["full_sha256"]),
            preimage_path=tmp_path / "unsafe.enc",
            recovery_secret=OLD_KEY,
        )
    assert not (tmp_path / "unsafe.enc").exists()


def test_partial_meta_or_whatsapp_inventory_is_rejected(
    credential_db: tuple[Session, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    session, _ = credential_db
    inventory = rekey.load_inventory(session)
    incomplete_meta = rekey.Inventory(
        meta_bindings=inventory.meta_bindings,
        meta_credentials=(),
        whatsapp_connections=inventory.whatsapp_connections,
        whatsapp_credentials=inventory.whatsapp_credentials,
    )
    with pytest.raises(RuntimeError, match="incomplete"):
        rekey.validate_inventory(incomplete_meta)

    connection = inventory.whatsapp_connections[0]
    connection.credential_generation += 1
    with pytest.raises(RuntimeError, match="invalid or partial"):
        rekey.validate_inventory(inventory)
    session.rollback()


def test_unreferenced_whatsapp_credential_inventory_is_rejected(
    credential_db: tuple[Session, Path],
) -> None:
    session, _ = credential_db
    connection = session.scalar(select(WhatsAppConnection))
    assert connection is not None
    session.add(
        WhatsAppCredential(
            id="stray-wa-credential-private-test-id",
            tenant_id=connection.tenant_id,
            connection_id=connection.id,
            generation=connection.credential_generation,
            ciphertext="v1.invalid-but-structurally-present",
            encryption_key_version="v1",
            token_type="user",
            scopes=[],
        )
    )
    session.flush()
    with pytest.raises(RuntimeError, match="invalid or partial"):
        rekey.validate_inventory(rekey.load_inventory(session))
    session.rollback()


def test_rekey_prepared_target_is_retry_stable_and_reconciles_source_or_target(
    credential_db: tuple[Session, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    session, tmp_path = credential_db
    monkeypatch.setattr(rekey, "_acquire_database_locks", lambda *_args, **_kwargs: None)
    source = _fingerprint(session)
    preimage = tmp_path / "resumable-preimage.enc"
    prepared_targets: list[str] = []

    def prepared_before_any_update(source_fp: dict[str, object], target_fp: dict[str, object]) -> None:
        assert _fingerprint(session) == source_fp
        _assert_decrypts_with(session, OLD_KEY)
        prepared_targets.append(str(target_fp["full_sha256"]))

    rekey.apply_rekey_transaction(
        session,
        old_secret=OLD_KEY,
        new_secret=NEW_KEY,
        new_key_version=KEY_VERSION,
        expected_current_sha256=str(source["full_sha256"]),
        preimage_path=preimage,
        recovery_secret=RECOVERY_KEY,
        transaction_id=TX_ID,
        before_updates=prepared_before_any_update,
    )
    # Model a commit failure/SIGKILL after the prepared certificate callback.
    session.rollback()
    assert _fingerprint(session) == source
    certified_target = prepared_targets[0]

    _, resumed = rekey.apply_rekey_transaction(
        session,
        old_secret=OLD_KEY,
        new_secret=NEW_KEY,
        new_key_version=KEY_VERSION,
        expected_current_sha256=str(source["full_sha256"]),
        preimage_path=preimage,
        recovery_secret=RECOVERY_KEY,
        transaction_id=TX_ID,
        certified_target_sha256=certified_target,
        before_updates=lambda _source, target: prepared_targets.append(str(target["full_sha256"])),
    )
    session.commit()
    assert str(resumed["full_sha256"]) == certified_target
    assert prepared_targets == [certified_target, certified_target]

    # A retry after a successful commit finalizes idempotently instead of
    # requiring the now-old runtime key to decrypt the target.
    before, already_committed = rekey.apply_rekey_transaction(
        session,
        old_secret=OLD_KEY,
        new_secret=NEW_KEY,
        new_key_version=KEY_VERSION,
        expected_current_sha256=str(source["full_sha256"]),
        preimage_path=preimage,
        recovery_secret=RECOVERY_KEY,
        transaction_id=TX_ID,
        certified_target_sha256=certified_target,
    )
    assert before == source
    assert already_committed == resumed


def test_rollback_prepared_target_resumes_after_commit_failure(
    credential_db: tuple[Session, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    session, tmp_path = credential_db
    monkeypatch.setattr(rekey, "_acquire_database_locks", lambda *_args, **_kwargs: None)
    original = _fingerprint(session)
    preimage_path = tmp_path / "rollback-source.enc"
    _, rekeyed = rekey.apply_rekey_transaction(
        session,
        old_secret=OLD_KEY,
        new_secret=NEW_KEY,
        new_key_version=KEY_VERSION,
        expected_current_sha256=str(original["full_sha256"]),
        preimage_path=preimage_path,
        recovery_secret=RECOVERY_KEY,
        transaction_id=TX_ID,
    )
    session.commit()
    preimage = rekey.read_preimage(preimage_path, recovery_secret=RECOVERY_KEY)
    pre_rollback = tmp_path / "resumable-pre-rollback.enc"
    prepared_targets: list[str] = []

    rekey.restore_preimage_transaction(
        session,
        current_secret=NEW_KEY,
        restored_secret=OLD_KEY,
        expected_current_sha256=str(rekeyed["full_sha256"]),
        preimage=preimage,
        pre_rollback_path=pre_rollback,
        recovery_secret=RECOVERY_KEY,
        before_updates=lambda _source, target: prepared_targets.append(str(target["full_sha256"])),
    )
    session.rollback()
    assert _fingerprint(session) == rekeyed

    _, restored = rekey.restore_preimage_transaction(
        session,
        current_secret=NEW_KEY,
        restored_secret=OLD_KEY,
        expected_current_sha256=str(rekeyed["full_sha256"]),
        preimage=preimage,
        pre_rollback_path=pre_rollback,
        recovery_secret=RECOVERY_KEY,
        certified_target_sha256=prepared_targets[0],
    )
    session.commit()
    assert restored == original

    source, already_restored = rekey.restore_preimage_transaction(
        session,
        current_secret=NEW_KEY,
        restored_secret=OLD_KEY,
        expected_current_sha256=str(rekeyed["full_sha256"]),
        preimage=preimage,
        pre_rollback_path=pre_rollback,
        recovery_secret=RECOVERY_KEY,
        certified_target_sha256=str(original["full_sha256"]),
    )
    assert source == rekeyed
    assert already_restored == original


def test_mixed_active_and_valid_disconnected_tombstone_rekeys_and_rolls_back(
    credential_db: tuple[Session, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    session, tmp_path = credential_db
    monkeypatch.setattr(rekey, "_acquire_database_locks", lambda *_args, **_kwargs: None)
    session.add(
        MetaAssetBindingRow(
            binding_id="disconnected-tombstone-private-id",
            tenant_id="tenant-private-test",
            channel="instagram",
            asset_id="instagram-private-test",
            page_id="page-private-test",
            instagram_account_id="instagram-private-test",
            app_key="linas_first_party",
            credential_id="removed-credential-lineage-private-id",
            status="disconnected",
            generation=2,
            created_at=5,
            updated_at=6,
            authorized_meta_user_id_hash="0123456789abcdef",
            auth_flow="instagram_login",
        )
    )
    session.commit()
    before = _fingerprint(session)
    preimage_path = tmp_path / "tombstone-preimage.enc"

    _, rekeyed = rekey.apply_rekey_transaction(
        session,
        old_secret=OLD_KEY,
        new_secret=NEW_KEY,
        new_key_version=KEY_VERSION,
        expected_current_sha256=str(before["full_sha256"]),
        preimage_path=preimage_path,
        recovery_secret=RECOVERY_KEY,
    )
    session.commit()
    assert rekeyed["structural_sha256"] == before["structural_sha256"]
    current = _fingerprint(session)
    _, restored = rekey.restore_preimage_transaction(
        session,
        current_secret=NEW_KEY,
        restored_secret=OLD_KEY,
        expected_current_sha256=str(current["full_sha256"]),
        preimage=rekey.read_preimage(preimage_path, recovery_secret=RECOVERY_KEY),
        pre_rollback_path=tmp_path / "tombstone-pre-rollback.enc",
        recovery_secret=RECOVERY_KEY,
    )
    session.commit()
    assert restored == before


def test_malformed_disconnected_tombstone_is_rejected(credential_db: tuple[Session, Path]) -> None:
    session, _ = credential_db
    session.add(
        MetaAssetBindingRow(
            binding_id="bad-tombstone-private-id",
            tenant_id="tenant-private-test",
            channel="facebook",
            asset_id="page-private-test-2",
            page_id="page-private-test-2",
            instagram_account_id="",
            app_key="linas_first_party",
            credential_id="missing-private-credential",
            status="disconnected",
            generation=2,
            created_at=5,
            updated_at=6,
            authorized_meta_user_id_hash="",
        )
    )
    session.flush()
    with pytest.raises(RuntimeError, match="incomplete"):
        rekey.validate_inventory(rekey.load_inventory(session))
    session.rollback()


def test_disconnected_tombstone_requires_removed_credential_lineage(
    credential_db: tuple[Session, Path],
) -> None:
    session, _ = credential_db
    session.add(
        MetaAssetBindingRow(
            binding_id="unlineaged-tombstone-private-id",
            tenant_id="tenant-private-test",
            channel="facebook",
            asset_id="page-private-test-3",
            page_id="page-private-test-3",
            instagram_account_id="",
            app_key="linas_first_party",
            credential_id="",
            status="disconnected",
            generation=2,
            created_at=5,
            updated_at=6,
            authorized_meta_user_id_hash="0123456789abcdef",
        )
    )
    session.flush()
    with pytest.raises(RuntimeError, match="incomplete"):
        rekey.validate_inventory(rekey.load_inventory(session))
    session.rollback()


def test_whatsapp_connection_without_credential_is_partial_inventory(
    credential_db: tuple[Session, Path],
) -> None:
    session, _ = credential_db
    session.add(
        WhatsAppConnection(
            id="wa-unowned-private-test-id",
            tenant_id="tenant-private-test",
            created_by_user_id="owner-private-test",
            meta_app_key="linas_first_party",
            meta_app_id="2963733803971681",
            waba_id="waba-private-test-2",
            phone_number_id="phone-private-test-2",
            lifecycle_status="disconnected",
            credential_id=None,
            credential_generation=1,
        )
    )
    session.flush()
    with pytest.raises(RuntimeError, match="WhatsApp connection credential inventory is incomplete"):
        rekey.validate_inventory(rekey.load_inventory(session))
    session.rollback()


def test_credentialless_tombstone_rejects_stray_credential_for_same_owner(
    credential_db: tuple[Session, Path],
) -> None:
    session, _ = credential_db
    binding = MetaAssetBindingRow(
        binding_id="stray-tombstone-private-id",
        tenant_id="tenant-private-test",
        channel="instagram",
        asset_id="instagram-private-test-2",
        page_id="page-private-test-3",
        instagram_account_id="instagram-private-test-2",
        app_key="linas_first_party",
        credential_id="deleted-credential-lineage-private-id",
        status="disconnected",
        generation=2,
        created_at=5,
        updated_at=6,
        authorized_meta_user_id_hash="0123456789abcdef",
        auth_flow="instagram_login",
    )
    session.add(binding)
    session.add(
        MetaBindingCredentialRow(
            credential_id="stray-private-credential-id",
            binding_id=binding.binding_id,
            sealed="v1.invalid-but-structurally-present",
            aad=f"{binding.binding_id}:stray-private-credential-id:1",
            created_at=5,
            archived_at=0,
        )
    )
    session.flush()
    with pytest.raises(RuntimeError, match="invalid or partial"):
        rekey.validate_inventory(rekey.load_inventory(session))
    session.rollback()


def test_concurrent_database_rekey_lock_fails_closed() -> None:
    class FakeSession:
        def get_bind(self):  # type: ignore[no-untyped-def]
            return SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))

        def scalar(self, *_args, **_kwargs):  # type: ignore[no-untyped-def]
            return False

    with pytest.raises(RuntimeError, match="another cross-product"):
        rekey._acquire_database_locks(FakeSession(), apply=True)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("apply", "expected_mode"),
    ((False, "IN SHARE MODE NOWAIT"), (True, "IN ACCESS EXCLUSIVE MODE NOWAIT")),
)
def test_database_inventory_table_locks_are_atomic_and_fail_fast(apply: bool, expected_mode: str) -> None:
    statements: list[str] = []

    class FakeSession:
        def get_bind(self):  # type: ignore[no-untyped-def]
            return SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))

        def scalar(self, *_args, **_kwargs):  # type: ignore[no-untyped-def]
            return True

        def execute(self, statement, *_args, **_kwargs):  # type: ignore[no-untyped-def]
            statements.append(str(statement))
            return None

    rekey._acquire_database_locks(FakeSession(), apply=apply)  # type: ignore[arg-type]
    assert any("pg_advisory_xact_lock" in statement for statement in statements)
    assert any(expected_mode in statement for statement in statements)


def test_runtime_env_refuses_file_dual_or_implicit_registry_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tmp_path.chmod(0o700)
    env_path = tmp_path / "runtime.env"
    for backend in ("file", "dual", ""):
        env_path.write_text(
            f"META_REGISTRY_BACKEND={backend}\n"
            f"META_CREDENTIAL_ENCRYPTION_KEY={OLD_KEY}\n"
            "LINAS_WHATSAPP_DATABASE_URL=postgresql://redacted.invalid/app\n",
            encoding="utf-8",
        )
        env_path.chmod(0o600)
        with pytest.raises(RuntimeError, match="prohibited"):
            rekey._load_runtime_env(env_path)
    monkeypatch.delenv("META_REGISTRY_BACKEND", raising=False)


def test_new_and_recovery_key_files_are_single_purpose(tmp_path: Path) -> None:
    tmp_path.chmod(0o700)
    new_key = tmp_path / "new.env"
    new_key.write_text(
        f"META_CREDENTIAL_ENCRYPTION_KEY={NEW_KEY}\nUNRELATED=value\n",
        encoding="utf-8",
    )
    new_key.chmod(0o600)
    with pytest.raises(RuntimeError, match="only"):
        rekey._load_new_runtime_key(new_key)

    recovery = tmp_path / "recovery.env"
    recovery.write_text(
        f"CREDENTIAL_REKEY_RECOVERY_KEY={RECOVERY_KEY}\nUNRELATED=value\n",
        encoding="utf-8",
    )
    recovery.chmod(0o600)
    with pytest.raises(RuntimeError, match="only"):
        rekey._load_recovery_key(recovery)

    proof = tmp_path / "proof.env"
    proof.write_text(
        f"CREDENTIAL_REKEY_PROOF_KEY={PROOF_KEY}\nUNRELATED=value\n",
        encoding="utf-8",
    )
    proof.chmod(0o600)
    with pytest.raises(RuntimeError, match="only"):
        rekey._load_proof_key(proof)


def test_confirmation_tokens_bind_all_keys_digest_and_transaction() -> None:
    current = "1" * 64
    args = (KEY_VERSION, NODE_VERIFICATION_KEYS)
    base = rekey.rekey_confirmation(current, NEW_KEY, RECOVERY_KEY, PROOF_KEY, TX_ID, *args)
    assert base.startswith("REKEY_META_WHATSAPP_")
    assert base != rekey.rekey_confirmation(current, NEW_KEY + "x", RECOVERY_KEY, PROOF_KEY, TX_ID, *args)
    assert base != rekey.rekey_confirmation(current, NEW_KEY, RECOVERY_KEY + "x", PROOF_KEY, TX_ID, *args)
    assert base != rekey.rekey_confirmation(current, NEW_KEY, RECOVERY_KEY, PROOF_KEY + "x", TX_ID, *args)
    assert base != rekey.rekey_confirmation("2" * 64, NEW_KEY, RECOVERY_KEY, PROOF_KEY, TX_ID, *args)
    assert base != rekey.rekey_confirmation(
        current,
        NEW_KEY,
        RECOVERY_KEY,
        PROOF_KEY,
        TX_ID,
        KEY_VERSION + "-different",
        NODE_VERIFICATION_KEYS,
    )
    rollback = rekey.rollback_confirmation(
        current,
        "2" * 64,
        OLD_KEY,
        RECOVERY_KEY,
        PROOF_KEY,
        "original-independent-proof-key-tests-97531",
        TX_ID,
        NODE_VERIFICATION_KEYS,
    )
    assert rollback != rekey.rollback_confirmation(
        current,
        "2" * 64,
        OLD_KEY,
        RECOVERY_KEY,
        PROOF_KEY,
        "different-original-proof-key-tests-86420",
        TX_ID,
        NODE_VERIFICATION_KEYS,
    )
    with pytest.raises(ValueError, match="freshly generated"):
        rekey._require_fresh_rollback_proof_key(PROOF_KEY, PROOF_KEY)
    rekey._require_fresh_rollback_proof_key(PROOF_KEY, "different-original-proof-key-tests-86420")


def _write_env(path: Path, *, node_id: str, key: str = OLD_KEY) -> None:
    path.write_text(
        "META_REGISTRY_BACKEND=postgres\n"
        f"META_CREDENTIAL_ENCRYPTION_KEY={key}\n"
        "LINAS_WHATSAPP_DATABASE_URL=postgresql://redacted.invalid/app\n"
        f"META_DELETION_NODE_ID={node_id}\n"
        "META_DELETION_REQUIRED_NODES=node01,node02\n"
        "META_HA_LB_READY_HEALTHCHECK_APPROVED=true\n"
        "LINAS_MAINTENANCE_DRAIN_FILE=/var/lib/linasbot/meta-ha/maintenance\n",
        encoding="utf-8",
    )
    path.chmod(0o600)


def test_env_backup_is_exactly_resumable_after_crash_before_proof(tmp_path: Path) -> None:
    tmp_path.chmod(0o700)
    source = tmp_path / "node01.env"
    backup = tmp_path / "node01.before"
    _write_env(source, node_id="node01")
    first_sha = rekey._copy_no_clobber(source, backup)

    # A retry after the backup was fsynced but before its proof was written
    # authenticates the immutable exact copy instead of dead-ending offline.
    assert rekey._copy_no_clobber(source, backup) == first_sha
    backup.write_bytes(backup.read_bytes() + b"TAMPERED=1\n")
    backup.chmod(0o600)
    with pytest.raises(RuntimeError, match="verification"):
        rekey._copy_no_clobber(source, backup)


def test_signed_offline_proofs_require_both_nodes_and_exact_env_backups(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tmp_path.chmod(0o700)
    env01 = tmp_path / "node01.env"
    env02 = tmp_path / "node02.env"
    _write_env(env01, node_id="node01")
    _write_env(env02, node_id="node02")
    monkeypatch.setattr(rekey, "_load_runtime_env", lambda path: (rekey._parse_env(path), OLD_KEY))
    common = {
        "transaction_id": TX_ID,
        "now": 1000,
        "unit_checker": lambda _unit: True,
        "port_checker": lambda: True,
        "marker_checker": lambda: None,
        "canonical_env_checker": lambda _path: None,
        "identity_checker": lambda node_id: HOST_IDENTITIES[node_id],
        "guard_checker": lambda **kwargs: _guard_sha(str(kwargs["node_id"])),
        "verification_keys": NODE_VERIFICATION_KEYS,
    }
    proof01 = rekey.build_offline_proof(
        env_path=env01,
        node_id="node01",
        env_backup_path=tmp_path / "node01.before",
        proof_secret=PROOF_KEY,
        signing_key=NODE_SIGNING_KEYS["node01"],
        **common,
    )
    proof02 = rekey.build_offline_proof(
        env_path=env02,
        node_id="node02",
        env_backup_path=tmp_path / "node02.before",
        proof_secret=PROOF_KEY,
        signing_key=NODE_SIGNING_KEYS["node02"],
        **common,
    )
    path01 = tmp_path / "node01.proof"
    path02 = tmp_path / "node02.proof"
    rekey._write_json_no_clobber(path01, proof01)
    rekey._write_json_no_clobber(path02, proof02)
    assert tuple(
        sorted(
            rekey.validate_offline_proofs(
                [path01, path02],
                proof_secret=PROOF_KEY,
                verification_keys=NODE_VERIFICATION_KEYS,
                runtime_secret=OLD_KEY,
                transaction_id=TX_ID,
                now=1001,
            )
        )
    ) == (
        "node01",
        "node02",
    )
    with pytest.raises(PermissionError, match="two HA"):
        rekey.validate_offline_proofs(
            [path01],
            proof_secret=PROOF_KEY,
            verification_keys=NODE_VERIFICATION_KEYS,
            runtime_secret=OLD_KEY,
            transaction_id=TX_ID,
            now=1001,
        )
    with pytest.raises(PermissionError, match="stale"):
        rekey.validate_offline_proofs(
            [path01, path02],
            proof_secret=PROOF_KEY,
            verification_keys=NODE_VERIFICATION_KEYS,
            runtime_secret=OLD_KEY,
            transaction_id=TX_ID,
            now=2000,
        )

    forged = json.loads(path02.read_text(encoding="utf-8"))
    forged_body = {key: value for key, value in forged.items() if key not in {"signature", "node_signature"}}
    path02.write_text(json.dumps(rekey._sign_proof(forged_body, OLD_KEY)), encoding="utf-8")
    path02.chmod(0o600)
    with pytest.raises(PermissionError, match="authentication"):
        rekey.validate_offline_proofs(
            [path01, path02],
            proof_secret=PROOF_KEY,
            verification_keys=NODE_VERIFICATION_KEYS,
            runtime_secret=OLD_KEY,
            transaction_id=TX_ID,
            now=1001,
        )

    # The coordinator's node01 private key cannot mint a node02 attestation,
    # even though both nodes intentionally share the ephemeral HMAC proof key.
    with pytest.raises(PermissionError, match="does not match"):
        rekey._attach_node_signature(
            rekey._sign_proof(forged_body, PROOF_KEY),
            node_id="node02",
            signing_key=NODE_SIGNING_KEYS["node01"],
            verification_keys=NODE_VERIFICATION_KEYS,
        )

    tampered = json.loads(path01.read_text(encoding="utf-8"))
    tampered["node_id"] = "node02"
    tampered["all_runtime_units_offline"] = False
    path02.write_text(json.dumps(tampered), encoding="utf-8")
    path02.chmod(0o600)
    with pytest.raises(PermissionError, match="authentication"):
        rekey.validate_offline_proofs(
            [path01, path02],
            proof_secret=PROOF_KEY,
            verification_keys=NODE_VERIFICATION_KEYS,
            runtime_secret=OLD_KEY,
            transaction_id=TX_ID,
            now=1001,
        )


def test_durable_database_certificate_authorizes_stale_bound_offline_proofs(tmp_path: Path) -> None:
    tmp_path.chmod(0o700)
    proof_paths: list[Path] = []
    proof_map: dict[str, dict[str, object]] = {}
    for node_id, backup_character in zip(rekey.REQUIRED_NODES, ("3", "4"), strict=True):
        body = {
            "format": rekey.PROOF_FORMAT,
            "transaction_id": TX_ID,
            "node_id": node_id,
            "created_at": 1000,
            "expires_at": 1000 + rekey.PROOF_MAX_AGE_SECONDS,
            "backend": "postgres",
            "required_nodes": list(rekey.REQUIRED_NODES),
            "persistent_maintenance": True,
            "all_runtime_units_offline": True,
            "application_ports_closed": True,
            "lb_health_path": "/api/ready",
            "runtime_guard_path": str(rekey.REKEY_GUARD_MARKER),
            "runtime_guard_transaction_id": TX_ID,
            "runtime_guarded_units": list(rekey.GUARDED_SYSTEMD_UNITS),
            "runtime_guard_sha256": _guard_sha(node_id),
            "host_identity": HOST_IDENTITIES[node_id],
            "verification_set_fingerprint": rekey._verification_set_fingerprint(NODE_VERIFICATION_KEYS),
            "node_verification_key_fingerprint": rekey._verification_key_fingerprint(NODE_VERIFICATION_KEYS[node_id]),
            "key_fingerprint": rekey._key_fingerprint(OLD_KEY),
            "env_backup_sha256": backup_character * 64,
        }
        proof = rekey._attach_node_signature(
            rekey._sign_proof(body, PROOF_KEY),
            node_id=node_id,
            signing_key=NODE_SIGNING_KEYS[node_id],
            verification_keys=NODE_VERIFICATION_KEYS,
        )
        path = tmp_path / f"{node_id}.durable-offline-proof"
        rekey._write_json_no_clobber(path, proof)
        proof_paths.append(path)
        proof_map[node_id] = proof

    with pytest.raises(PermissionError, match="stale"):
        rekey.validate_offline_proofs(
            proof_paths,
            proof_secret=PROOF_KEY,
            verification_keys=NODE_VERIFICATION_KEYS,
            runtime_secret=OLD_KEY,
            transaction_id=TX_ID,
            now=2000,
        )
    source = {"full_sha256": "5" * 64, "structural_sha256": "6" * 64}
    target = {"full_sha256": "7" * 64, "structural_sha256": "6" * 64}
    certificate = rekey._build_database_transition_certificate(
        operation="rekey",
        transaction_id=TX_ID,
        source_secret=OLD_KEY,
        target_secret=NEW_KEY,
        source_fingerprint=source,
        target_fingerprint=target,
        proof_secret=PROOF_KEY,
        signing_key=NODE_SIGNING_KEYS["node01"],
        verification_keys=NODE_VERIFICATION_KEYS,
        offline_proofs=proof_map,
        offline_proof_digests=rekey._proof_artifact_digests(
            proof_paths,
            proof_map,
            label="HA offline proof",
        ),
        artifact_digests={"credential_preimage": "8" * 64},
    )
    certificate_path = tmp_path / "database-transition-certificate.json"
    rekey._write_json_no_clobber(certificate_path, certificate)
    validated, certificate_sha = rekey.validate_database_transition_certificate(
        certificate_path,
        proof_secret=PROOF_KEY,
        verification_keys=NODE_VERIFICATION_KEYS,
        source_secret=OLD_KEY,
        target_secret=NEW_KEY,
        transaction_id=TX_ID,
        source_database_sha=str(source["full_sha256"]),
        target_database_sha=str(target["full_sha256"]),
        operation="rekey",
        offline_proof_paths=proof_paths,
    )
    assert set(validated) == set(rekey.REQUIRED_NODES)
    assert len(certificate_sha) == 64


def test_environment_proofs_bind_node_key_database_and_transaction(tmp_path: Path) -> None:
    tmp_path.chmod(0o700)
    database_sha = "b" * 64
    database_certificate_sha = "f" * 64
    proofs: list[Path] = []
    for node_id in rekey.REQUIRED_NODES:
        body = {
            "format": rekey.ENV_PROOF_FORMAT,
            "transaction_id": TX_ID,
            "node_id": node_id,
            "created_at": 1000,
            "expires_at": 1000 + rekey.PROOF_MAX_AGE_SECONDS,
            "database_sha256": database_sha,
            "database_transition_certificate_sha256": database_certificate_sha,
            "key_fingerprint": rekey._key_fingerprint(NEW_KEY),
            "environment_sha256": "c" * 64,
            "cluster_meta_fingerprint": "d" * 64,
            "persistent_maintenance": True,
            "all_runtime_units_offline": True,
            "runtime_guard_path": str(rekey.REKEY_GUARD_MARKER),
            "runtime_guard_transaction_id": TX_ID,
            "runtime_guarded_units": list(rekey.GUARDED_SYSTEMD_UNITS),
            "runtime_guard_sha256": _guard_sha(node_id),
            "host_identity": HOST_IDENTITIES[node_id],
            "verification_set_fingerprint": rekey._verification_set_fingerprint(NODE_VERIFICATION_KEYS),
            "node_verification_key_fingerprint": rekey._verification_key_fingerprint(NODE_VERIFICATION_KEYS[node_id]),
        }
        proof = rekey._attach_node_signature(
            rekey._sign_proof(body, PROOF_KEY, environment=True),
            node_id=node_id,
            signing_key=NODE_SIGNING_KEYS[node_id],
            verification_keys=NODE_VERIFICATION_KEYS,
        )
        path = tmp_path / f"{node_id}.env-proof"
        rekey._write_json_no_clobber(path, proof)
        proofs.append(path)
    assert (
        len(
            rekey.validate_env_proofs(
                proofs,
                proof_secret=PROOF_KEY,
                verification_keys=NODE_VERIFICATION_KEYS,
                runtime_secret=NEW_KEY,
                transaction_id=TX_ID,
                database_sha=database_sha,
                database_certificate_sha=database_certificate_sha,
                now=1001,
            )
        )
        == 2
    )
    with pytest.raises(PermissionError, match="stale"):
        rekey.validate_env_proofs(
            proofs,
            proof_secret=PROOF_KEY,
            verification_keys=NODE_VERIFICATION_KEYS,
            runtime_secret=NEW_KEY,
            transaction_id=TX_ID,
            database_sha=database_sha,
            database_certificate_sha=database_certificate_sha,
            now=2000,
        )
    assert len(
        rekey.validate_env_proofs(
            proofs,
            proof_secret=PROOF_KEY,
            verification_keys=NODE_VERIFICATION_KEYS,
            runtime_secret=NEW_KEY,
            transaction_id=TX_ID,
            database_sha=database_sha,
            database_certificate_sha=database_certificate_sha,
            now=2000,
            require_fresh=False,
        )
    ) == len(rekey.REQUIRED_NODES)
    original_second = proofs[1].read_bytes()
    forged_peer_body = {
        key: value
        for key, value in json.loads(proofs[0].read_text(encoding="utf-8")).items()
        if key not in {"signature", "node_signature"}
    }
    forged_peer_body.update(
        {
            "node_id": "node02",
            "host_identity": HOST_IDENTITIES["node02"],
            "runtime_guard_sha256": _guard_sha("node02"),
            "node_verification_key_fingerprint": rekey._verification_key_fingerprint(NODE_VERIFICATION_KEYS["node02"]),
        }
    )
    forged_peer = rekey._sign_proof(forged_peer_body, PROOF_KEY, environment=True)
    forged_peer["node_signature"] = rekey._b64encode(NODE_SIGNING_KEYS["node01"].sign(rekey._canonical(forged_peer)))
    proofs[1].write_text(json.dumps(forged_peer), encoding="utf-8")
    proofs[1].chmod(0o600)
    with pytest.raises(PermissionError, match="node signature"):
        rekey.validate_env_proofs(
            proofs,
            proof_secret=PROOF_KEY,
            verification_keys=NODE_VERIFICATION_KEYS,
            runtime_secret=NEW_KEY,
            transaction_id=TX_ID,
            database_sha=database_sha,
            database_certificate_sha=database_certificate_sha,
            now=1001,
        )
    proofs[1].write_bytes(original_second)
    proofs[1].chmod(0o600)

    second = json.loads(proofs[1].read_text(encoding="utf-8"))
    second_body = {key: value for key, value in second.items() if key not in {"signature", "node_signature"}}
    second_body["cluster_meta_fingerprint"] = "e" * 64
    proofs[1].write_text(
        json.dumps(
            rekey._attach_node_signature(
                rekey._sign_proof(second_body, PROOF_KEY, environment=True),
                node_id="node02",
                signing_key=NODE_SIGNING_KEYS["node02"],
                verification_keys=NODE_VERIFICATION_KEYS,
            )
        ),
        encoding="utf-8",
    )
    proofs[1].chmod(0o600)
    with pytest.raises(PermissionError, match="not identical"):
        rekey.validate_env_proofs(
            proofs,
            proof_secret=PROOF_KEY,
            verification_keys=NODE_VERIFICATION_KEYS,
            runtime_secret=NEW_KEY,
            transaction_id=TX_ID,
            database_sha=database_sha,
            database_certificate_sha=database_certificate_sha,
            now=1001,
        )
    with pytest.raises(PermissionError, match="authentication"):
        rekey.validate_env_proofs(
            proofs,
            proof_secret=OLD_KEY,
            verification_keys=NODE_VERIFICATION_KEYS,
            runtime_secret=NEW_KEY,
            transaction_id=TX_ID,
            database_sha=database_sha,
            database_certificate_sha=database_certificate_sha,
            now=1001,
        )


def test_transaction_guard_blocks_manual_start_and_survives_reboot_until_release(tmp_path: Path) -> None:
    marker_parent = tmp_path / "guard-state"
    marker_parent.mkdir(mode=0o700)
    marker = marker_parent / "runtime.guard"
    systemd_root = tmp_path / "systemd"
    systemd_root.mkdir(mode=0o755)

    def loaded(_unit: str, _path: Path) -> bool:
        return True

    def identity(_node: str) -> dict[str, str]:
        return HOST_IDENTITIES["node01"]

    dropins = _provision_static_guard(systemd_root, marker)
    guard_sha = rekey._arm_transaction_guard(
        node_id="node01",
        transaction_id=TX_ID,
        proof_secret=PROOF_KEY,
        marker_path=marker,
        systemd_root=systemd_root,
        reload_systemd=lambda: None,
        loaded_checker=loaded,
        identity_checker=identity,
    )
    assert guard_sha == hashlib.sha256(marker.read_bytes()).hexdigest()
    for dropin in dropins.values():
        content = dropin.read_text(encoding="utf-8")
        assert f"ConditionPathExists=!{marker}" in content
        # systemd's negated existence condition is false while the marker is
        # present, so a manual start and a boot-time start both fail closed.
        condition_result = not marker.exists()
        assert condition_result is False

    # A fresh validation models systemd reloading the persistent /etc + /var/lib
    # state after reboot; no volatile process snapshot is involved.
    assert (
        rekey._validate_transaction_guard(
            node_id="node01",
            transaction_id=TX_ID,
            proof_secret=PROOF_KEY,
            marker_path=marker,
            systemd_root=systemd_root,
            loaded_checker=loaded,
            identity_checker=identity,
        )
        == guard_sha
    )

    rekey._remove_transaction_guard(
        node_id="node01",
        transaction_id=TX_ID,
        proof_secret=PROOF_KEY,
        marker_path=marker,
        systemd_root=systemd_root,
        reload_systemd=lambda: None,
        loaded_checker=loaded,
        identity_checker=identity,
    )
    assert not marker.exists()
    assert all(path.read_bytes() == rekey._guard_dropin_payload(marker) for path in dropins.values())


@pytest.mark.parametrize("installed_count", range(len(rekey.GUARDED_SYSTEMD_UNITS)))
def test_transaction_guard_never_arms_after_partial_static_contract(tmp_path: Path, installed_count: int) -> None:
    marker_parent = tmp_path / "guard-state"
    marker_parent.mkdir(mode=0o700)
    marker = marker_parent / "runtime.guard"
    systemd_root = tmp_path / "systemd"
    systemd_root.mkdir(mode=0o755)
    payload = rekey._guard_dropin_payload(marker)
    dropins = list(rekey._guard_dropin_paths(systemd_root).values())

    # A crash after any partial prefix of the one-time pre-provisioning cannot
    # publish a transaction
    # marker.  With no marker, the static negated condition still permits the
    # normal runtime; the incomplete contract cannot attest an offline node.
    for dropin in dropins[:installed_count]:
        dropin.parent.mkdir(mode=0o755)
        dropin.write_bytes(payload)
        dropin.chmod(0o644)
    with pytest.raises(FileNotFoundError):
        rekey._arm_transaction_guard(
            node_id="node01",
            transaction_id=TX_ID,
            proof_secret=PROOF_KEY,
            marker_path=marker,
            systemd_root=systemd_root,
            loaded_checker=lambda _unit, _path: True,
            identity_checker=lambda _node: HOST_IDENTITIES["node01"],
        )
    assert not marker.exists()

    for dropin in dropins[installed_count:]:
        dropin.parent.mkdir(mode=0o755)
        dropin.write_bytes(payload)
        dropin.chmod(0o644)
    rekey._arm_transaction_guard(
        node_id="node01",
        transaction_id=TX_ID,
        proof_secret=PROOF_KEY,
        marker_path=marker,
        systemd_root=systemd_root,
        loaded_checker=lambda _unit, _path: True,
        identity_checker=lambda _node: HOST_IDENTITIES["node01"],
    )
    assert marker.exists()


def test_transaction_guard_tamper_fails_closed(tmp_path: Path) -> None:
    marker_parent = tmp_path / "guard-state"
    marker_parent.mkdir(mode=0o700)
    marker = marker_parent / "runtime.guard"
    systemd_root = tmp_path / "systemd"
    systemd_root.mkdir(mode=0o755)

    def identity(_node: str) -> dict[str, str]:
        return HOST_IDENTITIES["node01"]

    _provision_static_guard(systemd_root, marker)
    rekey._arm_transaction_guard(
        node_id="node01",
        transaction_id=TX_ID,
        proof_secret=PROOF_KEY,
        marker_path=marker,
        systemd_root=systemd_root,
        reload_systemd=lambda: None,
        loaded_checker=lambda _unit, _path: True,
        identity_checker=identity,
    )
    changed = next(iter(rekey._guard_dropin_paths(systemd_root).values()))
    changed.write_text("[Unit]\nConditionPathExists=!/wrong\n", encoding="utf-8")
    changed.chmod(0o644)
    with pytest.raises(PermissionError, match="changed"):
        rekey._validate_transaction_guard(
            node_id="node01",
            transaction_id=TX_ID,
            proof_secret=PROOF_KEY,
            marker_path=marker,
            systemd_root=systemd_root,
            loaded_checker=lambda _unit, _path: True,
            identity_checker=identity,
        )


def test_static_guard_asset_matches_runtime_contract() -> None:
    repository_root = Path(rekey.__file__).resolve().parents[2]
    asset = repository_root / "deploy/systemd/95-linasbot-credential-rekey-guard.conf"
    assert asset.read_bytes() == rekey._guard_dropin_payload()


def test_static_guard_preflight_rejects_stock_node_before_maintenance(tmp_path: Path) -> None:
    marker_parent = tmp_path / "guard-state"
    marker_parent.mkdir(mode=0o700)
    marker = marker_parent / "runtime.guard"
    systemd_root = tmp_path / "systemd"
    systemd_root.mkdir(mode=0o755)
    with pytest.raises(FileNotFoundError):
        rekey._validate_static_guard_contract(
            marker_path=marker,
            systemd_root=systemd_root,
            loaded_checker=lambda _unit, _path: True,
        )
    assert not marker.exists()


def test_guard_release_receipt_survives_crash_and_marker_removal_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    marker_parent = tmp_path / "guard-state"
    marker_parent.mkdir(mode=0o700)
    marker = marker_parent / "runtime.guard"
    systemd_root = tmp_path / "systemd"
    systemd_root.mkdir(mode=0o755)
    dropins = _provision_static_guard(systemd_root, marker)
    identity = HOST_IDENTITIES["node01"]
    monkeypatch.setattr(rekey, "_attest_host_identity", lambda _node: identity)
    guard_sha = rekey._arm_transaction_guard(
        node_id="node01",
        transaction_id=TX_ID,
        proof_secret=PROOF_KEY,
        marker_path=marker,
        systemd_root=systemd_root,
        loaded_checker=lambda _unit, _path: True,
        identity_checker=lambda _node: identity,
    )
    database_sha = "3" * 64
    env_proofs_sha = "4" * 64
    certificate_sha = "5" * 64
    confirmation = "RELEASE_REKEY_GUARD_NODE01_TEST"
    receipt = rekey._build_release_receipt(
        node_id="node01",
        transaction_id=TX_ID,
        database_sha=database_sha,
        runtime_secret=NEW_KEY,
        proof_secret=PROOF_KEY,
        guard_sha=guard_sha,
        env_proofs_sha=env_proofs_sha,
        database_certificate_sha=certificate_sha,
        confirmation=confirmation,
        signing_key=NODE_SIGNING_KEYS["node01"],
        verification_keys=NODE_VERIFICATION_KEYS,
    )
    receipt_path = marker_parent / "release-receipt.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    receipt_path.chmod(0o600)
    expected = {
        "format": rekey.RELEASE_RECEIPT_FORMAT,
        "node_id": "node01",
        "transaction_id": TX_ID,
        "database_sha256": database_sha,
        "runtime_key_fingerprint": rekey._key_fingerprint(NEW_KEY),
        "proof_key_fingerprint": rekey._key_fingerprint(PROOF_KEY),
        "guard_sha256": guard_sha,
        "env_proofs_sha256": env_proofs_sha,
        "database_certificate_sha256": certificate_sha,
        "confirmation_sha256": hashlib.sha256(confirmation.encode()).hexdigest(),
    }

    # This is the crash boundary: the durable signed receipt exists while the
    # marker still blocks boot/manual start.  A retry authenticates the receipt
    # and can safely finish exactly the marker unlink.
    rekey._validate_release_receipt(
        receipt_path,
        expected=expected,
        proof_secret=PROOF_KEY,
        verification_keys=NODE_VERIFICATION_KEYS,
    )
    assert marker.exists()
    assert rekey._finalize_transaction_guard_release(
        node_id="node01",
        transaction_id=TX_ID,
        proof_secret=PROOF_KEY,
        marker_path=marker,
        systemd_root=systemd_root,
        loaded_checker=lambda _unit, _path: True,
        identity_checker=lambda _node: identity,
    )
    assert not marker.exists()
    assert all(path.exists() for path in dropins.values())

    rekey._validate_release_receipt(
        receipt_path,
        expected=expected,
        proof_secret=PROOF_KEY,
        verification_keys=NODE_VERIFICATION_KEYS,
    )
    assert not rekey._finalize_transaction_guard_release(
        node_id="node01",
        transaction_id=TX_ID,
        proof_secret=PROOF_KEY,
        marker_path=marker,
        systemd_root=systemd_root,
        loaded_checker=lambda _unit, _path: True,
        identity_checker=lambda _node: identity,
    )


def test_same_host_cannot_claim_peer_fixed_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rekey.socket, "gethostname", lambda: rekey.FIXED_NODE_IDENTITIES["node01"]["hostname"])
    monkeypatch.setattr(
        rekey,
        "_interface_addresses",
        lambda: {
            rekey.FIXED_NODE_IDENTITIES["node01"]["public_ip"],
            rekey.FIXED_NODE_IDENTITIES["node01"]["private_ip"],
        },
    )
    with pytest.raises(PermissionError, match="fixed HA node"):
        rekey._attest_host_identity("node02")


def test_guard_contract_verify_only_is_mutually_exclusive_with_apply() -> None:
    parser = rekey.build_parser()
    args = parser.parse_args(
        [
            "guard-contract",
            "--env-file",
            "/opt/linasbot/.env",
            "--node-id",
            "node01",
            "--verify-only",
        ]
    )
    assert args.verify_only is True
    assert args.apply is False
    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "guard-contract",
                "--env-file",
                "/opt/linasbot/.env",
                "--node-id",
                "node01",
                "--verify-only",
                "--apply",
            ]
        )


def test_cli_defaults_to_dry_run_and_error_output_never_includes_exception_text(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(rekey, "_require_root", lambda: None)
    monkeypatch.setattr(rekey, "_load_proof_key", lambda _path: PROOF_KEY)
    monkeypatch.setattr(rekey, "_load_node_signing_key", lambda _path: NODE_SIGNING_KEYS["node01"])
    monkeypatch.setattr(rekey, "_load_node_verification_keys", lambda _path: NODE_VERIFICATION_KEYS)
    env_path = tmp_path / "missing-secret-value"
    env_path.write_text("redacted-test-payload\n", encoding="utf-8")
    env_path.chmod(0o600)
    original_inspector = rekey.inspect_offline_contract
    monkeypatch.setattr(rekey, "inspect_offline_contract", lambda **_kwargs: ({}, OLD_KEY))
    assert (
        rekey.main(
            [
                "--lock-path",
                str(tmp_path / "lock"),
                "offline-proof",
                "--env-file",
                str(env_path),
                "--proof-key-file",
                str(tmp_path / "missing-proof-key"),
                "--node-signing-key-file",
                str(tmp_path / "missing-signing-key"),
                "--node-verification-keys-file",
                str(tmp_path / "missing-verification-keys"),
                "--env-backup",
                str(tmp_path / "backup"),
                "--output",
                str(tmp_path / "proof"),
                "--node-id",
                "node01",
                "--transaction-id",
                TX_ID,
            ]
        )
        == 0
    )
    assert "DRY-RUN" in capsys.readouterr().out
    monkeypatch.setattr(rekey, "inspect_offline_contract", original_inspector)
    assert (
        rekey.main(
            [
                "--lock-path",
                str(tmp_path / "lock"),
                "offline-proof",
                "--env-file",
                str(env_path),
                "--proof-key-file",
                str(tmp_path / "missing-proof-key"),
                "--node-signing-key-file",
                str(tmp_path / "missing-signing-key"),
                "--node-verification-keys-file",
                str(tmp_path / "missing-verification-keys"),
                "--env-backup",
                str(tmp_path / "backup"),
                "--output",
                str(tmp_path / "proof"),
                "--node-id",
                "node01",
                "--transaction-id",
                TX_ID,
                "--apply",
            ]
        )
        == 2
    )
    error = capsys.readouterr().err
    assert any(kind in error for kind in ("PermissionError", "FileNotFoundError", "RuntimeError"))
    assert "missing-secret-value" not in error


@pytest.mark.parametrize(
    "name",
    ("controlled-failover.active", "registry-nfs-retire.active"),
)
def test_rekey_refuses_reciprocal_durable_ha_collision_paths(tmp_path: Path, name: str) -> None:
    collision = tmp_path / name
    collision.write_text("active\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="another durable HA transaction"):
        rekey._require_no_conflicting_ha_transaction((collision,))


def test_rekey_refuses_a_dangling_ha_collision_symlink(tmp_path: Path) -> None:
    collision = tmp_path / "registry-nfs-retire.active"
    collision.symlink_to(tmp_path / "missing")
    with pytest.raises(RuntimeError, match="another durable HA transaction"):
        rekey._require_no_conflicting_ha_transaction((collision,))
