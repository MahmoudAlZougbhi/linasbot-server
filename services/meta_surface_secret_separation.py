"""Fail closed when Instagram and Facebook Meta secrets are identical.

Compares signing secrets and webhook verify tokens only when both sides of a
pair are present. Missing/legacy empty values are not collisions. Messages and
reason codes never include secret values.
"""

from __future__ import annotations

import hmac
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

FACEBOOK_SIGNING_KEYS = ("META_APP_A_SECRET", "META_APP_SECRET")
FACEBOOK_VERIFY_KEYS = ("META_APP_A_WEBHOOK_VERIFY_TOKEN", "META_WEBHOOK_VERIFY_TOKEN")
INSTAGRAM_SIGNING_KEY = "META_INSTAGRAM_LOGIN_APP_SECRET"
INSTAGRAM_VERIFY_KEY = "META_INSTAGRAM_LOGIN_WEBHOOK_VERIFY_TOKEN"
SIGNING_COLLISION = "instagram_signing_matches_facebook"
VERIFY_COLLISION = "instagram_verify_matches_facebook"
COLLISION_EXIT = "instagram and facebook secrets must be distinct"
CONFIG_COLLISION_KEY = "META_INSTAGRAM_FACEBOOK_SECRET_COLLISION"


@dataclass(frozen=True)
class MetaSurfaceSecretSeparation:
    ok: bool
    collisions: tuple[str, ...]


def _first_present(values: Mapping[str, str], keys: tuple[str, ...]) -> str:
    for key in keys:
        raw = str(values.get(key) or "").strip().strip("'").strip('"')
        if raw:
            return raw
    return ""


def _secrets_equal(left: str, right: str) -> bool:
    if not left or not right or len(left) != len(right):
        return False
    return hmac.compare_digest(left, right)


def env_file_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if key:
            values[key] = value
    return values


def environ_secret_values() -> dict[str, str]:
    keys = (
        *FACEBOOK_SIGNING_KEYS,
        *FACEBOOK_VERIFY_KEYS,
        INSTAGRAM_SIGNING_KEY,
        INSTAGRAM_VERIFY_KEY,
    )
    return {key: (os.getenv(key) or "") for key in keys}


def evaluate_meta_surface_secret_separation(
    values: Mapping[str, str],
) -> MetaSurfaceSecretSeparation:
    facebook_signing = _first_present(values, FACEBOOK_SIGNING_KEYS)
    facebook_verify = _first_present(values, FACEBOOK_VERIFY_KEYS)
    instagram_signing = _first_present(values, (INSTAGRAM_SIGNING_KEY,))
    instagram_verify = _first_present(values, (INSTAGRAM_VERIFY_KEY,))
    collisions: list[str] = []
    if _secrets_equal(instagram_signing, facebook_signing):
        collisions.append(SIGNING_COLLISION)
    if _secrets_equal(instagram_verify, facebook_verify):
        collisions.append(VERIFY_COLLISION)
    return MetaSurfaceSecretSeparation(ok=not collisions, collisions=tuple(collisions))


def require_separated_meta_surface_secrets(values: Mapping[str, str]) -> None:
    result = evaluate_meta_surface_secret_separation(values)
    if not result.ok:
        raise SystemExit(COLLISION_EXIT)


def require_separated_meta_surface_secrets_for_update(
    env_path: Path,
    proposed: Mapping[str, str],
) -> None:
    merged = env_file_values(env_path)
    merged.update({str(key): str(value) for key, value in proposed.items()})
    require_separated_meta_surface_secrets(merged)
