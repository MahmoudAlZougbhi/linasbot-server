"""Defaults for Linas AI model routing (gpt-5.6 luna/sol + image/video)."""

from __future__ import annotations

from services.cm.answer_generation import DEFAULT_CM_ANSWER_MODEL, cm_answer_model
from services.owner_ai_model_router import route_owner_turn, router_config
from services.providers.base import provider_config


def test_provider_config_defaults_are_strong_models(monkeypatch) -> None:
    for key in (
        "LINAS_MODEL_CUSTOMER_DM",
        "LINAS_MODEL_OWNER_CHAT",
        "LINAS_MODEL_SETUP",
        "LINAS_MODEL_CREATIVE",
        "LINAS_IMAGE_MODEL",
        "LINAS_IMAGE_PROVIDER",
        "LINAS_VIDEO_MODEL",
        "LINAS_VIDEO_PROVIDER",
    ):
        monkeypatch.delenv(key, raising=False)

    cfg = provider_config()
    assert cfg["text"]["customer_dm"] == "gpt-5.6-luna"
    assert cfg["text"]["owner_chat"] == "gpt-5.6-sol"
    assert cfg["text"]["setup_complex"] == "gpt-5.6-sol"
    assert cfg["text"]["creative_text"] == "gpt-5.6-sol"
    assert cfg["image"]["model"] == "gpt-image-2"
    assert cfg["image"]["provider"] == "openai"
    assert cfg["video"]["model"] == "sora-2-pro"
    assert cfg["video"]["provider"] == "openai"


def test_owner_router_defaults_sol_and_luna(monkeypatch) -> None:
    for key in (
        "LINAS_OWNER_HELP_MODEL",
        "LINAS_OWNER_CM_MODEL",
        "LINAS_CREATIVE_MODEL",
        "LINAS_CUSTOMER_HV_MODEL",
    ):
        monkeypatch.delenv(key, raising=False)

    cfg = router_config()
    assert cfg["owner_help"]["model"] == "gpt-5.6-luna"
    assert cfg["owner_complex_cm"]["model"] == "gpt-5.6-sol"
    assert cfg["creative"]["model"] == "gpt-5.6-sol"
    assert cfg["customer_high_volume"]["model"] == "gpt-5.6-luna"

    cm = route_owner_turn("publish my content management draft")
    assert cm.kind == "owner_complex_cm"
    assert cm.model == "gpt-5.6-sol"


def test_cm_answer_model_default_luna(monkeypatch) -> None:
    monkeypatch.delenv("LINAS_CM_ANSWER_MODEL", raising=False)
    monkeypatch.delenv("LINAS_MODEL_CUSTOMER_DM", raising=False)
    assert DEFAULT_CM_ANSWER_MODEL == "gpt-5.6-luna"
    assert cm_answer_model() == "gpt-5.6-luna"


def test_env_overrides_do_not_silently_fallback(monkeypatch) -> None:
    monkeypatch.setenv("LINAS_CM_ANSWER_MODEL", "gpt-5.6-luna")
    monkeypatch.setenv("LINAS_OWNER_CM_MODEL", "gpt-5.6-sol")
    monkeypatch.setenv("LINAS_IMAGE_MODEL", "gpt-image-2")
    assert cm_answer_model() == "gpt-5.6-luna"
    assert router_config()["owner_complex_cm"]["model"] == "gpt-5.6-sol"
    assert provider_config()["image"]["model"] == "gpt-image-2"
