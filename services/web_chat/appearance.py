"""Widget appearance defaults and validation."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Literal

IntegrationMode = Literal["linas_widget", "custom_chat"]
ThemeMode = Literal["light", "dark"]
Position = Literal["bottom_left", "bottom_right"]
SizePreset = Literal["compact", "standard", "large"]
CornerPreset = Literal["soft", "rounded", "extra_rounded"]
LauncherMode = Literal["icon", "icon_text"]

DEFAULT_APPEARANCE: dict[str, Any] = {
    "identity": {
        "display_name": "Chat with us",
        "logo_url": "",
        "welcome_message": "Hi! How can I help you today?",
        "subtitle": "We typically reply in minutes",
    },
    "theme": {
        "mode": "light",
        "accent_color": "#0D9488",
    },
    "bubbles": {
        "assistant_bg": "#FFFFFF",
        "assistant_text": "#0F172A",
        "visitor_bg": "#0D9488",
        "visitor_text": "#FFFFFF",
    },
    "layout": {
        "position": "bottom_right",
        "size": "standard",
        "corners": "rounded",
    },
    "launcher": {
        "mode": "icon",
        "text": "Chat",
    },
}

_ALLOWED: dict[str, set[str]] = {
    "theme.mode": {"light", "dark"},
    "layout.position": {"bottom_left", "bottom_right"},
    "layout.size": {"compact", "standard", "large"},
    "layout.corners": {"soft", "rounded", "extra_rounded"},
    "launcher.mode": {"icon", "icon_text"},
}


def _clamp_text(value: Any, *, max_len: int) -> str:
    text = str(value or "").strip()
    return text[:max_len]


def _normalize_hex(value: Any, fallback: str) -> str:
    text = str(value or "").strip()
    if len(text) == 7 and text.startswith("#"):
        try:
            int(text[1:], 16)
            return text.upper()
        except ValueError:
            return fallback
    return fallback


def _relative_luminance(hex_color: str) -> float:
    raw = hex_color.lstrip("#")
    if len(raw) != 6:
        return 0.5
    r, g, b = (int(raw[i : i + 2], 16) / 255 for i in (0, 2, 4))

    def channel(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = channel(r), channel(g), channel(b)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(fg: str, bg: str) -> float:
    l1 = _relative_luminance(fg)
    l2 = _relative_luminance(bg)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def contrast_warnings(appearance: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    bubbles = appearance.get("bubbles") or {}
    pairs = (
        ("assistant_text", "assistant_bg", "assistant"),
        ("visitor_text", "visitor_bg", "visitor"),
    )
    for fg_key, bg_key, label in pairs:
        fg = str(bubbles.get(fg_key) or "")
        bg = str(bubbles.get(bg_key) or "")
        if fg.startswith("#") and bg.startswith("#") and contrast_ratio(fg, bg) < 4.5:
            warnings.append(f"low_contrast_{label}")
    return warnings


def normalize_appearance(raw: dict[str, Any] | None) -> dict[str, Any]:
    base = deepcopy(DEFAULT_APPEARANCE)
    if not isinstance(raw, dict):
        return base

    identity = raw.get("identity") if isinstance(raw.get("identity"), dict) else {}
    theme = raw.get("theme") if isinstance(raw.get("theme"), dict) else {}
    bubbles = raw.get("bubbles") if isinstance(raw.get("bubbles"), dict) else {}
    launcher = raw.get("launcher") if isinstance(raw.get("launcher"), dict) else {}

    base["identity"]["display_name"] = _clamp_text(
        identity.get("display_name"), max_len=80
    ) or base["identity"]["display_name"]
    base["identity"]["logo_url"] = _clamp_text(identity.get("logo_url"), max_len=500)
    base["identity"]["welcome_message"] = _clamp_text(
        identity.get("welcome_message"), max_len=500
    ) or base["identity"]["welcome_message"]
    base["identity"]["subtitle"] = _clamp_text(identity.get("subtitle"), max_len=120)

    mode = str(theme.get("mode") or base["theme"]["mode"]).lower()
    base["theme"]["mode"] = mode if mode in _ALLOWED["theme.mode"] else base["theme"]["mode"]
    base["theme"]["accent_color"] = _normalize_hex(
        theme.get("accent_color"), base["theme"]["accent_color"]
    )

    for key, fallback_key in (
        ("assistant_bg", "assistant_bg"),
        ("assistant_text", "assistant_text"),
        ("visitor_bg", "visitor_bg"),
        ("visitor_text", "visitor_text"),
    ):
        base["bubbles"][key] = _normalize_hex(
            bubbles.get(key), DEFAULT_APPEARANCE["bubbles"][fallback_key]
        )

    for section, field, allowed in (
        ("layout", "position", "layout.position"),
        ("layout", "size", "layout.size"),
        ("layout", "corners", "layout.corners"),
    ):
        val = str((raw.get(section) or {}).get(field) or base[section][field]).lower()
        base[section][field] = val if val in _ALLOWED[allowed] else base[section][field]

    launcher_mode = str(launcher.get("mode") or base["launcher"]["mode"]).lower()
    base["launcher"]["mode"] = (
        launcher_mode if launcher_mode in _ALLOWED["launcher.mode"] else base["launcher"]["mode"]
    )
    base["launcher"]["text"] = _clamp_text(launcher.get("text"), max_len=40) or base["launcher"]["text"]
    return base


def normalize_integration_mode(raw: str | None) -> IntegrationMode:
    mode = str(raw or "linas_widget").strip().lower()
    if mode == "custom_chat":
        return "custom_chat"
    return "linas_widget"
