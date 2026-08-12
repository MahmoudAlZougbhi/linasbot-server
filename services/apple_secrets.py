"""Apple Sign-In + IAP private-key path helpers (never log key material)."""

from __future__ import annotations

import os
from pathlib import Path

_DEFAULT_SECRETS_DIR = Path.home() / ".linasai-secrets" / "apple"

_DEFAULT_SIGN_IN_KEY_ID = "5FK9G38WRJ"
_DEFAULT_SIGN_IN_KEY_PATH = _DEFAULT_SECRETS_DIR / f"AuthKey_{_DEFAULT_SIGN_IN_KEY_ID}.p8"

_DEFAULT_IAP_ISSUER_ID = "a3b052c7-c0ed-4935-8e2e-4b57946e1f6b"
_DEFAULT_IAP_KEY_ID = "8H9SZG552B"
_DEFAULT_IAP_KEY_PATH = _DEFAULT_SECRETS_DIR / f"SubscriptionKey_{_DEFAULT_IAP_KEY_ID}.p8"

_DEFAULT_TEAM_ID = "55624L5UXL"
_DEFAULT_BUNDLE_ID = "com.linasai.app"


def _expand(path: str) -> Path:
    return Path(path).expanduser().resolve()


def read_private_key_pem(path: str) -> str:
    """Read a .p8 PEM file. Fail closed if missing/empty. Never log contents."""
    p = _expand(path)
    if not p.is_file():
        raise FileNotFoundError(f"Apple private key file not found: {p}")
    try:
        text = p.read_text(encoding="utf-8")
    except OSError as exc:
        raise FileNotFoundError(f"Apple private key unreadable: {p}") from exc
    if "PRIVATE KEY" not in text or not text.strip():
        raise ValueError(f"Apple private key file invalid or empty: {p}")
    return text


def apple_sign_in_key_path() -> str:
    raw = (os.getenv("APPLE_SIGN_IN_PRIVATE_KEY_PATH") or "").strip()
    if raw:
        return str(_expand(raw))
    return str(_DEFAULT_SIGN_IN_KEY_PATH)


def apple_iap_key_path() -> str:
    raw = (
        os.getenv("APPLE_IAP_PRIVATE_KEY_PATH")
        or os.getenv("APPLE_APP_STORE_PRIVATE_KEY_PATH")
        or ""
    ).strip()
    if raw:
        return str(_expand(raw))
    return str(_DEFAULT_IAP_KEY_PATH)


def apple_team_id() -> str:
    return (os.getenv("APPLE_TEAM_ID") or _DEFAULT_TEAM_ID).strip()


def apple_bundle_id() -> str:
    return (os.getenv("APPLE_BUNDLE_ID") or _DEFAULT_BUNDLE_ID).strip()


def apple_sign_in_key_id() -> str:
    return (os.getenv("APPLE_SIGN_IN_KEY_ID") or _DEFAULT_SIGN_IN_KEY_ID).strip()


def apple_iap_key_id() -> str:
    return (
        os.getenv("APPLE_IAP_KEY_ID") or os.getenv("APPLE_APP_STORE_KEY_ID") or _DEFAULT_IAP_KEY_ID
    ).strip()


def apple_iap_issuer_id() -> str:
    return (
        os.getenv("APPLE_IAP_ISSUER_ID")
        or os.getenv("APPLE_APP_STORE_ISSUER_ID")
        or _DEFAULT_IAP_ISSUER_ID
    ).strip()


def _home_relative(path: str) -> str:
    p = Path(path)
    try:
        return str(Path("~") / p.relative_to(Path.home()))
    except ValueError:
        return str(p)


def secrets_status() -> dict:
    """Booleans + paths + key ids only — never key material."""
    sign_path = apple_sign_in_key_path()
    iap_path = apple_iap_key_path()
    return {
        "auth_key_exists": Path(sign_path).is_file(),
        "iap_key_exists": Path(iap_path).is_file(),
        "auth_key_path": _home_relative(sign_path),
        "iap_key_path": _home_relative(iap_path),
        "sign_in_key_id": apple_sign_in_key_id(),
        "iap_key_id": apple_iap_key_id(),
        "iap_issuer_id": apple_iap_issuer_id(),
        "team_id": apple_team_id(),
        "bundle_id": apple_bundle_id(),
    }
