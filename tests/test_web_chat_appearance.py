"""Web Chat appearance and domain helpers."""

from __future__ import annotations

import pytest

from services.web_chat.appearance import (
    DEFAULT_APPEARANCE,
    contrast_ratio,
    contrast_warnings,
    normalize_appearance,
    normalize_integration_mode,
)
from services.web_chat.domain import normalize_site_url, origin_allowed_for_site


def test_normalize_site_url_accepts_bare_domain() -> None:
    assert normalize_site_url("example.com") == "https://example.com"


def test_origin_allows_www_variant() -> None:
    assert origin_allowed_for_site("https://example.com", "https://www.example.com")
    assert origin_allowed_for_site("https://www.shop.test", "https://shop.test")


def test_origin_rejects_foreign_host() -> None:
    assert not origin_allowed_for_site("https://example.com", "https://evil.com")


def test_legacy_appearance_defaults() -> None:
    out = normalize_appearance(None)
    assert out["identity"]["display_name"] == DEFAULT_APPEARANCE["identity"]["display_name"]
    assert out["theme"]["accent_color"] == "#0D9488"


def test_contrast_warnings_low_pair() -> None:
    appearance = normalize_appearance(
        {
            "bubbles": {
                "assistant_bg": "#FFFFFF",
                "assistant_text": "#EEEEEE",
                "visitor_bg": "#0D9488",
                "visitor_text": "#FFFFFF",
            }
        }
    )
    warnings = contrast_warnings(appearance)
    assert "low_contrast_assistant" in warnings


def test_contrast_ratio_order_independent() -> None:
    assert contrast_ratio("#000000", "#FFFFFF") == pytest.approx(contrast_ratio("#FFFFFF", "#000000"))


def test_integration_mode_normalization() -> None:
    assert normalize_integration_mode("custom_chat") == "custom_chat"
    assert normalize_integration_mode("unknown") == "linas_widget"
