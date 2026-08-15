from __future__ import annotations

import json
import os
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.audit_meta_app_a_scopes import (
    FACEBOOK_LOGIN_REVIEW_SCOPES,
    FACEBOOK_REVIEW_SCOPES,
    _load_runtime_environment,
    _print_debug_permission_statuses,
    _select_required_social_bindings,
)


def test_page_debug_scope_gate_does_not_require_integration_token_scope() -> None:
    assert FACEBOOK_LOGIN_REVIEW_SCOPES == {"business_management"}
    assert "business_management" not in FACEBOOK_REVIEW_SCOPES


def test_scope_audit_dotenv_values_are_data_not_shell(tmp_path: Path) -> None:
    marker = tmp_path / "must-not-exist"
    env_file = tmp_path / ".env"
    env_file.write_text(
        "META_APP_ID=2963733803971681\n"
        "LINAS_CUSTOMER_ANSWER_MODEL=Linas AI production model\n"
        f"UNTRUSTED_SHELL_TEXT=$(touch {marker})\n",
        encoding="utf-8",
    )
    names = ("META_APP_ID", "LINAS_CUSTOMER_ANSWER_MODEL", "UNTRUSTED_SHELL_TEXT")
    missing = object()
    original = {name: os.environ.get(name, missing) for name in names}
    for name in names:
        os.environ.pop(name, None)

    try:
        loaded = _load_runtime_environment(env_file)

        assert loaded == env_file
        assert not marker.exists()
        assert os.environ["META_APP_ID"] == "2963733803971681"
        assert os.environ["LINAS_CUSTOMER_ANSWER_MODEL"] == "Linas AI production model"
        assert os.environ["UNTRUSTED_SHELL_TEXT"] == f"$(touch {marker})"
    finally:
        # python-dotenv mutates os.environ outside pytest's monkeypatch tracker;
        # restore the process environment explicitly so the audit regression
        # cannot poison later model-policy or application-startup tests.
        for name, value in original.items():
            if value is missing:
                os.environ.pop(name, None)
            else:
                os.environ[name] = str(value)


def test_scope_audit_dotenv_does_not_override_injected_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("META_APP_ID=unexpected\n", encoding="utf-8")
    monkeypatch.setenv("META_APP_ID", "2963733803971681")

    _load_runtime_environment(env_file)

    assert os.environ["META_APP_ID"] == "2963733803971681"


def test_scope_audit_rejects_missing_configured_dotenv(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="Configured scope-audit env file is missing"):
        _load_runtime_environment(tmp_path / "missing.env")


def test_direct_instagram_token_never_uses_facebook_debug_endpoint(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def unexpected_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("direct Instagram token crossed into Facebook debug_token")

    monkeypatch.setattr("urllib.request.urlopen", unexpected_network)
    result = _print_debug_permission_statuses(
        object(),
        auth_flow="instagram_login",
    )

    assert "skipped_direct_instagram_trust_domain" in capsys.readouterr().out
    assert result is None


@pytest.mark.parametrize(
    ("is_valid", "missing_scope", "expected"),
    [(True, None, True), (False, None, False), (True, "pages_manage_engagement", False)],
)
def test_facebook_live_scope_proof_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    is_valid: bool,
    missing_scope: str | None,
    expected: bool,
) -> None:
    scopes = sorted(FACEBOOK_REVIEW_SCOPES - ({missing_scope} if missing_scope else set()))
    payload = json.dumps({"data": {"is_valid": is_valid, "scopes": scopes}}).encode()

    class Response(BytesIO):
        def __enter__(self) -> Response:
            return self

        def __exit__(self, *_args: object) -> None:
            self.close()

    monkeypatch.setenv("META_APP_ID", "2963733803971681")
    monkeypatch.setenv("META_APP_SECRET", "secret")
    monkeypatch.setattr("urllib.request.urlopen", lambda *_args, **_kwargs: Response(payload))
    credential = SimpleNamespace(access_token="page-token", declined_scopes=())

    assert (
        _print_debug_permission_statuses(
            credential,
            auth_flow="facebook_login",
            required_scopes=FACEBOOK_REVIEW_SCOPES,
        )
        is expected
    )


def _binding(tenant: str, channel: str, auth_flow: str, asset_id: str) -> SimpleNamespace:
    return SimpleNamespace(
        tenant_id=tenant,
        channel=channel,
        auth_flow=auth_flow,
        asset_id=asset_id,
    )


def test_scope_audit_selects_exact_tenant_and_required_surfaces() -> None:
    facebook = _binding("linas", "facebook", "facebook_login", "378696005334409")
    instagram = _binding("linas", "instagram", "instagram_login", "17841413184256533")
    unrelated = _binding("other", "facebook", "facebook_login", "378696005334409")
    legacy_instagram = _binding("linas", "instagram", "facebook_login", "17841413184256533")

    selected, failures = _select_required_social_bindings(
        [unrelated, legacy_instagram, facebook, instagram],
        tenant_id="linas",
        expected_page_id="378696005334409",
        expected_instagram_id="17841413184256533",
    )

    assert selected == [facebook, instagram]
    assert failures == []


def test_scope_audit_fails_when_direct_instagram_surface_is_missing() -> None:
    facebook = _binding("linas", "facebook", "facebook_login", "378696005334409")

    selected, failures = _select_required_social_bindings(
        [facebook],
        tenant_id="linas",
        expected_page_id="378696005334409",
        expected_instagram_id="17841413184256533",
    )

    assert selected == [facebook]
    assert failures == ["required_binding_instagram_instagram_login_count_0"]


def test_scope_audit_fails_on_duplicate_required_surface() -> None:
    facebook = _binding("linas", "facebook", "facebook_login", "378696005334409")
    duplicate = _binding("linas", "facebook", "facebook_login", "378696005334409")
    instagram = _binding("linas", "instagram", "instagram_login", "17841413184256533")

    selected, failures = _select_required_social_bindings(
        [facebook, duplicate, instagram],
        tenant_id="linas",
        expected_page_id="378696005334409",
        expected_instagram_id="17841413184256533",
    )

    assert selected == [instagram]
    assert failures == ["required_binding_facebook_facebook_login_count_2"]
