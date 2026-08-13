"""Mobile app marketing-version config + public check API."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from modules.api_security import is_public_api
from services.mobile_app_version import compare_semver, evaluate_app_version, parse_semver


@pytest.fixture(scope="module")
def app_client() -> TestClient:
    import main  # noqa: F401
    from modules.core import app

    return TestClient(app)


class TestSemver:
    def test_parse_and_compare(self) -> None:
        assert parse_semver("1.0.0") == (1, 0, 0)
        assert parse_semver("v2.10.3") == (2, 10, 3)
        assert compare_semver("1.0.0", "1.0.1") == -1
        assert compare_semver("1.1.0", "1.0.9") == 1
        assert compare_semver("1.0.0", "1.0.0") == 0

    def test_rejects_invalid(self) -> None:
        with pytest.raises(ValueError):
            parse_semver("1.0")
        with pytest.raises(ValueError):
            parse_semver("not-a-version")


class TestEvaluate:
    def test_states(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MOBILE_APP_LATEST_VERSION", "1.1.0")
        monkeypatch.setenv("MOBILE_APP_MIN_SUPPORTED_VERSION", "1.0.0")

        assert evaluate_app_version("1.1.0")["state"] == "up_to_date"
        assert evaluate_app_version("1.0.5")["state"] == "update_available"
        assert evaluate_app_version("0.9.9")["state"] == "force_update"
        assert evaluate_app_version("2.0.0")["state"] == "up_to_date"


class TestPublicApi:
    def test_public_allowlist(self) -> None:
        assert is_public_api("GET", "/api/public/app-version")
        assert is_public_api("POST", "/api/public/app-version/check")

    def test_get_config(self, app_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MOBILE_APP_LATEST_VERSION", "1.0.1")
        monkeypatch.setenv("MOBILE_APP_MIN_SUPPORTED_VERSION", "1.0.0")
        response = app_client.get("/api/public/app-version")
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["latest_version"] == "1.0.1"
        assert body["min_supported_version"] == "1.0.0"
        assert body["ios_store_url"].startswith("https://")

    def test_check_requires_version(self, app_client: TestClient) -> None:
        response = app_client.post("/api/public/app-version/check", json={})
        assert response.status_code == 400

    def test_check_update_available(self, app_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MOBILE_APP_LATEST_VERSION", "1.0.2")
        monkeypatch.setenv("MOBILE_APP_MIN_SUPPORTED_VERSION", "1.0.0")
        response = app_client.post(
            "/api/public/app-version/check",
            json={"installed_version": "1.0.0", "platform": "ios"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["state"] == "update_available"
        assert body["installed_version"] == "1.0.0"
        assert body["latest_version"] == "1.0.2"

    def test_check_force_update(self, app_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MOBILE_APP_LATEST_VERSION", "2.0.0")
        monkeypatch.setenv("MOBILE_APP_MIN_SUPPORTED_VERSION", "1.5.0")
        response = app_client.post(
            "/api/public/app-version/check",
            json={"installed_version": "1.0.0"},
        )
        assert response.status_code == 200
        assert response.json()["state"] == "force_update"
