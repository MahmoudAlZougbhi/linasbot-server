"""Mobile app marketing-version config + semver compare (build numbers are client/EAS only)."""

from __future__ import annotations

import os
import re
from typing import Any, Literal

AppVersionState = Literal["up_to_date", "update_available", "force_update"]

_DEFAULT_LATEST = "1.0.0"
_DEFAULT_MIN = "1.0.0"
_DEFAULT_IOS_STORE_URL = "https://apps.apple.com/app/id6799678918"
_DEFAULT_ANDROID_STORE_URL = "https://play.google.com/store/apps/details?id=com.linasai.app"

_SEMVER_RE = re.compile(r"^v?(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)(?:[-+].*)?$", re.IGNORECASE)


class InvalidAppVersionError(ValueError):
    """Raised when a marketing version string is not semver X.Y.Z."""


def _clean_env(name: str, default: str) -> str:
    raw = (os.getenv(name) or default).strip()
    return raw or default


def _clean_url(name: str, default: str) -> str | None:
    raw = (os.getenv(name) or default).strip()
    if not raw:
        return None
    if not raw.startswith("https://"):
        raise ValueError(f"{name} must be an https URL when set")
    return raw


def parse_semver(value: str) -> tuple[int, int, int]:
    text = (value or "").strip()
    match = _SEMVER_RE.fullmatch(text)
    if not match:
        raise InvalidAppVersionError("installed_version must be semver major.minor.patch")
    return int(match.group("major")), int(match.group("minor")), int(match.group("patch"))


def compare_semver(left: str, right: str) -> int:
    """Return -1 if left < right, 0 if equal, 1 if left > right."""
    l_parts = parse_semver(left)
    r_parts = parse_semver(right)
    if l_parts < r_parts:
        return -1
    if l_parts > r_parts:
        return 1
    return 0


def app_version_config() -> dict[str, Any]:
    latest = _clean_env("MOBILE_APP_LATEST_VERSION", _DEFAULT_LATEST)
    minimum = _clean_env("MOBILE_APP_MIN_SUPPORTED_VERSION", _DEFAULT_MIN)
    parse_semver(latest)
    parse_semver(minimum)
    if compare_semver(minimum, latest) > 0:
        raise ValueError("MOBILE_APP_MIN_SUPPORTED_VERSION cannot exceed MOBILE_APP_LATEST_VERSION")
    return {
        "latest_version": latest,
        "min_supported_version": minimum,
        "ios_store_url": _clean_url("MOBILE_APP_IOS_STORE_URL", _DEFAULT_IOS_STORE_URL),
        "android_store_url": _clean_url("MOBILE_APP_ANDROID_STORE_URL", _DEFAULT_ANDROID_STORE_URL),
    }


def evaluate_app_version(installed_version: str) -> dict[str, Any]:
    cfg = app_version_config()
    installed = (installed_version or "").strip()
    parse_semver(installed)

    latest = cfg["latest_version"]
    minimum = cfg["min_supported_version"]

    if compare_semver(installed, minimum) < 0:
        state: AppVersionState = "force_update"
    elif compare_semver(installed, latest) < 0:
        state = "update_available"
    else:
        state = "up_to_date"

    return {
        "success": True,
        "state": state,
        "installed_version": installed,
        "latest_version": latest,
        "min_supported_version": minimum,
        "ios_store_url": cfg["ios_store_url"],
        "android_store_url": cfg["android_store_url"],
    }
