"""Unit tests for CM capability gates and Firebase readiness alignment."""

from __future__ import annotations

from pathlib import Path

import pytest

from modules.settings_api import _firebase_credentials_configured
from services.cm.capability_gates import human_handoff_enabled, image_analysis_enabled, voice_processing_enabled
from services.cm.schemas import AiLimitsSection


def test_firebase_credentials_configured_uses_data_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    key = tmp_path / "firebase_data.json"
    key.write_text("{}", encoding="utf-8")
    monkeypatch.delenv("FIRESTORE_SERVICE_ACCOUNT_KEY_PATH", raising=False)
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    monkeypatch.delenv("FIREBASE_CREDENTIALS_PATH", raising=False)
    monkeypatch.chdir(tmp_path)
    # Relative data/ path used by Live Chat init.
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "firebase_data.json").write_text("{}", encoding="utf-8")
    assert _firebase_credentials_configured() is True


def test_firebase_credentials_configured_uses_env_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    key = tmp_path / "sa.json"
    key.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("FIRESTORE_SERVICE_ACCOUNT_KEY_PATH", str(key))
    monkeypatch.chdir(tmp_path)
    assert _firebase_credentials_configured() is True


def test_capability_gates_read_published_ai_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("services.cm.capability_gates.tenant_uses_cm_runtime", lambda _tid: True)

    class _Pointer:
        content_version_id = "v_test"
        index_version_id = "idx_test"

    def _load(_tid: str):
        return _Pointer(), {
            "ai_limits": AiLimitsSection(
                voice_processing_enabled=False,
                image_analysis_enabled=True,
            ).model_dump(mode="json")
        }

    monkeypatch.setattr("services.cm.capability_gates.load_published_content", _load)
    assert voice_processing_enabled("linas") is False
    assert image_analysis_enabled("linas") is True


def test_human_handoff_enabled_prefers_ai_limits_field(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("services.cm.capability_gates.tenant_uses_cm_runtime", lambda _tid: True)

    class _Pointer:
        content_version_id = "v_test"
        index_version_id = "idx_test"

    def _load(_tid: str):
        return _Pointer(), {
            "ai_limits": {
                "human_handoff_enabled": False,
            },
            "actions": {
                "items": [{"id": "human_handoff", "enabled": True}],
            },
        }

    monkeypatch.setattr("services.cm.capability_gates.load_published_content", _load)
    assert human_handoff_enabled("linas") is False


def test_human_handoff_enabled_falls_back_to_actions_toggle(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("services.cm.capability_gates.tenant_uses_cm_runtime", lambda _tid: True)

    class _Pointer:
        content_version_id = "v_test"
        index_version_id = "idx_test"

    def _load(_tid: str):
        limits_data = AiLimitsSection().model_dump(mode="json")
        limits_data.pop("human_handoff_enabled", None)
        return _Pointer(), {
            "ai_limits": limits_data,
            "actions": {
                "items": [{"id": "human_handoff", "enabled": False}],
            },
        }

    monkeypatch.setattr("services.cm.capability_gates.load_published_content", _load)
    assert human_handoff_enabled("linas") is False
