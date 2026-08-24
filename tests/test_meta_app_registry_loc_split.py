"""LOC split: meta_app_registry common/bindings/lifecycle/oauth under 500 lines."""

from __future__ import annotations

from pathlib import Path

from services.meta_app_registry import (
    APP_A_KEY,
    MetaAppRegistry,
    MetaAssetBinding,
    MetaBindingCredential,
    MetaCredentialCipher,
    diagnose_active_meta_binding,
    get_meta_app_configs,
    get_meta_app_registry,
    get_meta_registry_readiness,
    meta_multi_app_registry_enabled,
)
from services.meta_app_registry_bindings import MetaAppRegistryBindingsMixin
from services.meta_app_registry_comment_permissions import MetaAppRegistryCommentPermissionsMixin
from services.meta_app_registry_lifecycle import MetaAppRegistryLifecycleMixin
from services.meta_app_registry_oauth import MetaAppRegistryOAuthMixin
from services.meta_app_registry_oauth_authorize import MetaAppRegistryOAuthAuthorizeMixin


def _line_count(rel: str) -> int:
    return len(Path(rel).read_text(encoding="utf-8").splitlines())


def test_meta_app_registry_modules_under_500_lines() -> None:
    assert _line_count("services/meta_app_registry.py") < 500
    assert _line_count("services/meta_app_registry_common.py") < 500
    assert _line_count("services/meta_app_registry_bindings.py") < 500
    assert _line_count("services/meta_app_registry_comment_permissions.py") < 500
    assert _line_count("services/meta_app_registry_backend.py") < 500
    assert _line_count("services/meta_app_registry_deletion.py") < 500
    assert _line_count("services/meta_app_registry_lifecycle.py") < 500
    assert _line_count("services/meta_app_registry_oauth.py") < 500
    assert _line_count("services/meta_app_registry_oauth_authorize.py") < 500


def test_meta_app_registry_preserves_public_api_via_mixins() -> None:
    assert issubclass(MetaAppRegistry, MetaAppRegistryBindingsMixin)
    assert issubclass(MetaAppRegistry, MetaAppRegistryCommentPermissionsMixin)
    assert issubclass(MetaAppRegistry, MetaAppRegistryLifecycleMixin)
    assert issubclass(MetaAppRegistry, MetaAppRegistryOAuthMixin)
    assert issubclass(MetaAppRegistry, MetaAppRegistryOAuthAuthorizeMixin)
    assert APP_A_KEY == "linas_first_party"
    assert callable(get_meta_app_configs)
    assert callable(get_meta_app_registry)
    assert callable(get_meta_registry_readiness)
    assert callable(diagnose_active_meta_binding)
    assert callable(meta_multi_app_registry_enabled)
    for name in (
        "authorize_oauth_asset",
        "activate_binding",
        "activate_staged_binding",
        "get_credential",
        "store_oauth_state",
        "consume_oauth_state",
    ):
        assert callable(getattr(MetaAppRegistry, name))
    assert MetaAssetBinding is not None
    assert MetaBindingCredential is not None
    assert MetaCredentialCipher is not None
