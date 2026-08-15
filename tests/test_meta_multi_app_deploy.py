"""Static safety gates for the canonical two-app production workflow."""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import seed_meta_app_a_registry
from scripts.validate_meta_social_token import EXPECTED_INSTAGRAM_ID, EXPECTED_PAGE_ID, REQUIRED_SCOPES
from services.meta_app_registry import APP_A_EXPECTED_ID, APP_A_KEY, MetaBindingCredential
from services.meta_facebook_scope_policy import FACEBOOK_PAGE_BINDING_SCOPES

ROOT = Path(__file__).resolve().parents[1]


def test_multi_app_apply_script_is_a_static_ha_stage() -> None:
    script = ROOT / "scripts/prod_apply_meta_multi_app.sh"
    subprocess.run(["bash", "-n", str(script)], check=True, capture_output=True, text=True)
    source = script.read_text(encoding="utf-8")
    assert "set -x" not in source
    assert 'echo "$META_' not in source
    assert "META_HA_STAGE_ONLY=true is required" in source
    assert "atomic_update_env" in source
    assert "APPLY_META_MULTI_APP_REGISTRY_ENABLED" in source
    assert "registry_activation_deferred_to_ha_sync=true" in source
    assert "direct_instagram_binding_seeded=false" in source
    assert "seed_meta_app_a_registry" not in source
    assert "systemctl" not in source
    assert "urllib" not in source
    assert "journalctl" not in source
    assert "META_APP_B_LINAS_CUTOVER_APPROVED" in source


def test_multi_app_workflow_uses_only_canonical_secret_names_and_no_auto_approval() -> None:
    source = (ROOT / ".github/workflows/meta-multi-app-secrets-apply.yml").read_text(encoding="utf-8")
    for secret_name in (
        "META_APP_ID",
        "META_APP_SECRET",
        "META_PAGE_ACCESS_TOKEN",
        "META_WEBHOOK_VERIFY_TOKEN",
        "META_CREDENTIAL_ENCRYPTION_KEY",
        "META_APP_B_ID",
        "META_APP_B_SECRET",
        "META_APP_B_WEBHOOK_VERIFY_TOKEN",
        "META_APP_B_LOGIN_CONFIG_ID",
    ):
        assert f"secrets.{secret_name}" in source
    assert 'META_APP_B_ADVANCED_ACCESS_APPROVED: "false"' in source
    assert "META_APP_B_LINAS_CUTOVER_APPROVED" not in source
    assert 'bash "$REPO_DIR/scripts/prod_apply_meta_multi_app.sh"' in source
    assert 'sudo -E bash "$REPO_DIR/scripts/prod_apply_meta_multi_app.sh"' not in source
    assert "export LINAS_PRODUCTION_MUTATION_LOCK_FD=9" in source
    assert "--register-prestage-backup" in source
    assert 'META_HA_STAGE_ONLY: "true"' in source
    assert "--maintenance-active" in source


def test_registry_seed_script_never_renders_credentials() -> None:
    source = (ROOT / "scripts/seed_meta_app_a_registry.py").read_text(encoding="utf-8")
    assert "print(page_token" not in source
    assert "print(app.app_secret" not in source
    assert 'print(f"{page_token' not in source
    assert 'print(f"{app.app_secret' not in source
    assert "app_a_id_match=true" in source
    assert "instagram_relationship_match=true" in source
    assert "direct_instagram_binding_seeded=false" in source
    assert 'channel="instagram"' not in source


def test_registry_seed_activates_only_the_facebook_page_binding(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("META_PAGE_ACCESS_TOKEN", "page-token")
    monkeypatch.setenv("META_CREDENTIAL_ENCRYPTION_KEY", "k" * 32)
    app = SimpleNamespace(
        enabled=True,
        app_id=APP_A_EXPECTED_ID,
        app_secret="app-secret",
        graph_api_version="v24.0",
    )
    monkeypatch.setattr(seed_meta_app_a_registry, "get_meta_app_configs", lambda: {APP_A_KEY: app})
    responses = iter(
        [
            {
                "data": {
                    "is_valid": True,
                    "app_id": APP_A_EXPECTED_ID,
                    "type": "PAGE",
                    "expires_at": 0,
                    "user_id": "123456789",
                    "scopes": sorted(
                        FACEBOOK_PAGE_BINDING_SCOPES
                        | {
                            "whatsapp_business_management",
                            "whatsapp_business_messaging",
                        }
                    ),
                    "granular_scopes": [{"scope": "pages_messaging", "target_ids": [EXPECTED_PAGE_ID]}],
                }
            },
            {
                "id": EXPECTED_PAGE_ID,
                "instagram_business_account": {"id": EXPECTED_INSTAGRAM_ID},
            },
        ]
    )
    monkeypatch.setattr(
        seed_meta_app_a_registry,
        "_request_json",
        lambda *_args, **_kwargs: next(responses),
    )

    activations: list[dict[str, object]] = []

    class FakeRegistry:
        def __init__(self, *, master_secret: str) -> None:
            assert master_secret == "k" * 32

        def get_active_bindings_for_app(self, app_key: str) -> list[object]:
            assert app_key == APP_A_KEY
            return [
                SimpleNamespace(
                    tenant_id="linas",
                    channel="facebook",
                    asset_id=EXPECTED_PAGE_ID,
                )
            ]

        def get_credential(self, _binding: object) -> MetaBindingCredential:
            # A pre-fix registry row can still contain valid WhatsApp coexistence
            # grants. The seed must rewrite it to the normalized Page-only set.
            return MetaBindingCredential(
                access_token="page-token",
                token_app_id=APP_A_EXPECTED_ID,
                token_profile_id=EXPECTED_PAGE_ID,
                scopes=tuple(
                    sorted(
                        FACEBOOK_PAGE_BINDING_SCOPES
                        | {
                            "whatsapp_business_management",
                            "whatsapp_business_messaging",
                        }
                    )
                ),
                authorized_meta_user_id="123456789",
            )

        def activate_binding(self, **kwargs: object) -> None:
            activations.append(kwargs)

    monkeypatch.setattr(seed_meta_app_a_registry, "MetaAppRegistry", FakeRegistry)

    seed_meta_app_a_registry.main()

    assert len(activations) == 1
    assert activations[0]["channel"] == "facebook"
    assert activations[0]["asset_id"] == EXPECTED_PAGE_ID
    assert activations[0]["instagram_account_id"] == EXPECTED_INSTAGRAM_ID
    credential = activations[0]["credential"]
    assert isinstance(credential, MetaBindingCredential)
    assert set(credential.scopes) == set(FACEBOOK_PAGE_BINDING_SCOPES)
    assert not any(scope.startswith("whatsapp_") for scope in credential.scopes)
    output = capsys.readouterr().out
    assert "direct_instagram_binding_seeded=false" in output


def test_registry_seed_rejects_legacy_instagram_grants_on_page_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("META_PAGE_ACCESS_TOKEN", "page-token")
    monkeypatch.setenv("META_CREDENTIAL_ENCRYPTION_KEY", "k" * 32)
    app = SimpleNamespace(
        enabled=True,
        app_id=APP_A_EXPECTED_ID,
        app_secret="app-secret",
        graph_api_version="v24.0",
    )
    monkeypatch.setattr(seed_meta_app_a_registry, "get_meta_app_configs", lambda: {APP_A_KEY: app})
    responses = iter(
        [
            {
                "data": {
                    "is_valid": True,
                    "app_id": APP_A_EXPECTED_ID,
                    "type": "PAGE",
                    "expires_at": 0,
                    "user_id": "123456789",
                    "scopes": sorted(REQUIRED_SCOPES | {"instagram_manage_comments"}),
                    "granular_scopes": [{"scope": "pages_messaging", "target_ids": [EXPECTED_PAGE_ID]}],
                }
            },
            {
                "id": EXPECTED_PAGE_ID,
                "instagram_business_account": {"id": EXPECTED_INSTAGRAM_ID},
            },
        ]
    )
    monkeypatch.setattr(
        seed_meta_app_a_registry,
        "_request_json",
        lambda *_args, **_kwargs: next(responses),
    )

    class ForbiddenRegistry:
        def __init__(self, **_kwargs: object) -> None:
            raise AssertionError("forbidden legacy Instagram grant must fail before persistence")

    monkeypatch.setattr(seed_meta_app_a_registry, "MetaAppRegistry", ForbiddenRegistry)

    with pytest.raises(seed_meta_app_a_registry.MetaTokenValidationError, match="prohibited"):
        seed_meta_app_a_registry.main()


def test_registry_seed_rejects_page_token_missing_comment_permission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("META_PAGE_ACCESS_TOKEN", "page-token")
    monkeypatch.setenv("META_CREDENTIAL_ENCRYPTION_KEY", "k" * 32)
    app = SimpleNamespace(
        enabled=True,
        app_id=APP_A_EXPECTED_ID,
        app_secret="app-secret",
        graph_api_version="v24.0",
    )
    monkeypatch.setattr(seed_meta_app_a_registry, "get_meta_app_configs", lambda: {APP_A_KEY: app})
    responses = iter(
        [
            {
                "data": {
                    "is_valid": True,
                    "app_id": APP_A_EXPECTED_ID,
                    "type": "PAGE",
                    "expires_at": 0,
                    "user_id": "123456789",
                    "scopes": sorted(FACEBOOK_PAGE_BINDING_SCOPES - {"pages_manage_engagement"}),
                    "granular_scopes": [{"scope": "pages_messaging", "target_ids": [EXPECTED_PAGE_ID]}],
                }
            },
            {
                "id": EXPECTED_PAGE_ID,
                "instagram_business_account": {"id": EXPECTED_INSTAGRAM_ID},
            },
        ]
    )
    monkeypatch.setattr(
        seed_meta_app_a_registry,
        "_request_json",
        lambda *_args, **_kwargs: next(responses),
    )

    class ForbiddenRegistry:
        def __init__(self, **_kwargs: object) -> None:
            raise AssertionError("incomplete Page review grant must fail before persistence")

    monkeypatch.setattr(seed_meta_app_a_registry, "MetaAppRegistry", ForbiddenRegistry)

    with pytest.raises(seed_meta_app_a_registry.MetaTokenValidationError, match="DM or comment"):
        seed_meta_app_a_registry.main()


def test_registry_seed_rejects_foreign_granular_page_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("META_PAGE_ACCESS_TOKEN", "page-token")
    monkeypatch.setenv("META_CREDENTIAL_ENCRYPTION_KEY", "k" * 32)
    app = SimpleNamespace(
        enabled=True,
        app_id=APP_A_EXPECTED_ID,
        app_secret="app-secret",
        graph_api_version="v24.0",
    )
    monkeypatch.setattr(seed_meta_app_a_registry, "get_meta_app_configs", lambda: {APP_A_KEY: app})
    responses = iter(
        [
            {
                "data": {
                    "is_valid": True,
                    "app_id": APP_A_EXPECTED_ID,
                    "type": "PAGE",
                    "expires_at": 0,
                    "user_id": "123456789",
                    "scopes": sorted(FACEBOOK_PAGE_BINDING_SCOPES),
                    "granular_scopes": [
                        {
                            "scope": "pages_manage_engagement",
                            "target_ids": [EXPECTED_PAGE_ID, "999888777"],
                        }
                    ],
                }
            },
            {
                "id": EXPECTED_PAGE_ID,
                "instagram_business_account": {"id": EXPECTED_INSTAGRAM_ID},
            },
        ]
    )
    monkeypatch.setattr(
        seed_meta_app_a_registry,
        "_request_json",
        lambda *_args, **_kwargs: next(responses),
    )

    class ForbiddenRegistry:
        def __init__(self, **_kwargs: object) -> None:
            raise AssertionError("foreign granular target must fail before persistence")

    monkeypatch.setattr(seed_meta_app_a_registry, "MetaAppRegistry", ForbiddenRegistry)

    with pytest.raises(seed_meta_app_a_registry.MetaTokenValidationError, match="another asset"):
        seed_meta_app_a_registry.main()
