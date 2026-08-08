"""Multi-page Meta binding upsert, archive, and isolation tests."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from services.meta_app_registry import (
    APP_A_KEY,
    MetaAppRegistry,
    MetaBindingCredential,
    authorized_meta_user_id_hash,
)
from services.social_user_id import compose_social_user_id, tenant_channel_has_multiple_active_assets

SCOPES = (
    "pages_show_list",
    "pages_manage_metadata",
    "pages_read_engagement",
    "pages_messaging",
    "instagram_basic",
    "instagram_manage_messages",
)


def _credential(page_id: str, *, user_id: str = "123456789") -> MetaBindingCredential:
    return MetaBindingCredential(
        access_token=f"token-{page_id}",
        token_app_id="2963733803971681",
        token_profile_id=page_id,
        scopes=SCOPES,
        expires_at=int(time.time()) + 3600,
        authorized_meta_user_id=user_id,
    )


@pytest.fixture
def registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> MetaAppRegistry:
    monkeypatch.setenv("META_APP_A_ID", "2963733803971681")
    monkeypatch.setenv("META_APP_A_SECRET", "app-a-secret-tests")
    monkeypatch.setenv("META_APP_A_WEBHOOK_VERIFY_TOKEN", "verify-a-tests")
    return MetaAppRegistry(
        store_path=tmp_path / "registry.json",
        audit_path=tmp_path / "audit.jsonl",
        master_secret="multi-page-registry-secret-tests-123456",
    )


def test_oauth_reauthorize_same_page_reuses_binding_without_duplicate(registry: MetaAppRegistry) -> None:
    page_id = "378696005334409"
    first = registry.authorize_oauth_asset(
        tenant_id="linas",
        channel="facebook",
        asset_id=page_id,
        page_id=page_id,
        instagram_account_id="17841413184256533",
        app_key=APP_A_KEY,
        credential=_credential(page_id),
        actor_id="owner",
        page_name="Lina's Laser Clinics",
        status="active",
    )
    registry.set_binding_status(first.binding_id, status="disconnected", actor_id="owner")
    second = registry.authorize_oauth_asset(
        tenant_id="linas",
        channel="facebook",
        asset_id=page_id,
        page_id=page_id,
        instagram_account_id="17841413184256533",
        app_key=APP_A_KEY,
        credential=_credential(page_id, user_id="123456789"),
        actor_id="owner",
        page_name="Lina's Laser Clinics",
        status="active",
    )
    visible = registry.list_bindings(include_superseded=False)
    facebook_rows = [row for row in visible if row.channel == "facebook"]
    assert second.binding_id == first.binding_id
    assert len(facebook_rows) == 1
    assert facebook_rows[0].status == "active"


def test_second_facebook_page_adds_new_binding(registry: MetaAppRegistry) -> None:
    first_page = "378696005334409"
    second_page = "445566778899"
    registry.authorize_oauth_asset(
        tenant_id="linas",
        channel="facebook",
        asset_id=first_page,
        page_id=first_page,
        instagram_account_id="",
        app_key=APP_A_KEY,
        credential=_credential(first_page),
        actor_id="owner",
        page_name="Lina's Laser Clinics",
    )
    registry.authorize_oauth_asset(
        tenant_id="linas",
        channel="facebook",
        asset_id=second_page,
        page_id=second_page,
        instagram_account_id="",
        app_key=APP_A_KEY,
        credential=_credential(second_page),
        actor_id="owner",
        page_name="Second Branch",
    )
    active = [
        row for row in registry.list_bindings(include_superseded=False) if row.channel == "facebook" and row.active
    ]
    assert len(active) == 2
    assert {row.asset_id for row in active} == {first_page, second_page}


def test_instagram_asset_binding_is_separate_from_facebook(registry: MetaAppRegistry) -> None:
    page_id = "378696005334409"
    instagram_id = "17841413184256533"
    registry.authorize_oauth_asset(
        tenant_id="linas",
        channel="facebook",
        asset_id=page_id,
        page_id=page_id,
        instagram_account_id=instagram_id,
        app_key=APP_A_KEY,
        credential=_credential(page_id),
        actor_id="owner",
        page_name="Lina's Laser Clinics",
    )
    registry.authorize_oauth_asset(
        tenant_id="linas",
        channel="instagram",
        asset_id=instagram_id,
        page_id=page_id,
        instagram_account_id=instagram_id,
        app_key=APP_A_KEY,
        credential=_credential(page_id),
        actor_id="owner",
        page_name="Lina's Laser Clinics",
        instagram_username="linasclinics",
    )
    visible = registry.list_bindings(include_superseded=False)
    assert len([row for row in visible if row.channel == "facebook"]) == 1
    assert len([row for row in visible if row.channel == "instagram"]) == 1


def test_archive_hides_legacy_duplicate_for_same_asset(registry: MetaAppRegistry) -> None:
    page_id = "378696005334409"
    old = registry.activate_binding(
        tenant_id="linas",
        channel="facebook",
        asset_id=page_id,
        page_id=page_id,
        instagram_account_id="",
        app_key=APP_A_KEY,
        credential=_credential(page_id),
        actor_id="owner",
        status="disconnected",
    )
    new = registry.activate_binding(
        tenant_id="linas",
        channel="facebook",
        asset_id=page_id,
        page_id=page_id,
        instagram_account_id="",
        app_key=APP_A_KEY,
        credential=_credential(page_id),
        actor_id="owner",
        status="active",
        replace_existing=True,
    )
    archived = registry.archive_superseded_duplicate_bindings()
    assert archived >= 1
    visible = registry.list_bindings(include_superseded=False)
    facebook_rows = [row for row in visible if row.channel == "facebook"]
    assert len(facebook_rows) == 1
    assert facebook_rows[0].binding_id == new.binding_id
    raw_old = next(binding for binding in registry.list_bindings() if binding.binding_id == old.binding_id)
    assert raw_old.superseded_by_binding_id == new.binding_id


def test_compose_user_id_scopes_by_asset_only_when_multiple_pages(registry: MetaAppRegistry) -> None:
    page_a = "111222333444"
    page_b = "555666777888"
    registry.authorize_oauth_asset(
        tenant_id="linas",
        channel="facebook",
        asset_id=page_a,
        page_id=page_a,
        instagram_account_id="",
        app_key=APP_A_KEY,
        credential=_credential(page_a),
        actor_id="owner",
    )
    assert (
        compose_social_user_id(
            tenant_id="linas",
            channel="facebook",
            asset_id=page_a,
            sender_id="999",
        )
        == "facebook:999"
    )
    registry.authorize_oauth_asset(
        tenant_id="linas",
        channel="facebook",
        asset_id=page_b,
        page_id=page_b,
        instagram_account_id="",
        app_key=APP_A_KEY,
        credential=_credential(page_b),
        actor_id="owner",
    )
    assert tenant_channel_has_multiple_active_assets("linas", "facebook") is True
    assert (
        compose_social_user_id(
            tenant_id="linas",
            channel="facebook",
            asset_id=page_a,
            sender_id="999",
        )
        == "facebook:111222333444:999"
    )


def test_cross_workspace_asset_conflict_is_rejected(registry: MetaAppRegistry) -> None:
    page_id = "378696005334409"
    registry.authorize_oauth_asset(
        tenant_id="linas",
        channel="facebook",
        asset_id=page_id,
        page_id=page_id,
        instagram_account_id="",
        app_key=APP_A_KEY,
        credential=_credential(page_id),
        actor_id="owner",
    )
    with pytest.raises(Exception, match="another workspace"):
        registry.authorize_oauth_asset(
            tenant_id="tenant-b",
            channel="facebook",
            asset_id=page_id,
            page_id=page_id,
            instagram_account_id="",
            app_key=APP_A_KEY,
            credential=_credential(page_id, user_id="987654321"),
            actor_id="owner-b",
        )


def test_authorized_meta_user_id_hash_never_contains_raw_id() -> None:
    digest = authorized_meta_user_id_hash("123456789")
    assert "123456789" not in digest
    assert len(digest) == 16
