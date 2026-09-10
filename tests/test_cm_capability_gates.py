"""Unit tests for CM capability gates."""

from __future__ import annotations

import pytest

from services.cm.capability_gates import human_handoff_enabled, image_analysis_enabled, voice_processing_enabled
from services.cm.schemas import AiLimitsSection


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


def test_human_handoff_follows_published_human_request_rule(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("services.cm.capability_gates.tenant_uses_cm_runtime", lambda _tid: True)

    class _Pointer:
        content_version_id = "v_test"
        index_version_id = "idx_test"

    def _load(_tid: str):
        return _Pointer(), {
            "ai_limits": {"human_handoff_enabled": False},
            "requests_appointments": {
                "rules": [{"id": "h1", "type": "HUMAN", "name": "Staff", "enabled": True}],
            },
        }

    monkeypatch.setattr("services.cm.capability_gates.load_published_content", _load)
    assert human_handoff_enabled("linas") is True


def test_disabled_human_request_rule_blocks_handoff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("services.cm.capability_gates.tenant_uses_cm_runtime", lambda _tid: True)

    class _Pointer:
        content_version_id = "v_test"
        index_version_id = "idx_test"

    def _load(_tid: str):
        return _Pointer(), {
            "ai_limits": {"human_handoff_enabled": True},
            "requests_appointments": {
                "rules": [{"id": "h1", "type": "HUMAN", "name": "Staff", "enabled": False}],
            },
        }

    monkeypatch.setattr("services.cm.capability_gates.load_published_content", _load)
    assert human_handoff_enabled("linas") is False
