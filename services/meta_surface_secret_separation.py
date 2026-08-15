"""Fail closed when Instagram and Facebook Meta secrets are identical.

Compares every simultaneously present Facebook signing alias against every
present Instagram signing alias, and every present Facebook verify alias
against every present Instagram verify alias. Simultaneously present Facebook
aliases must also agree with each other. First-present precedence is not used.
Missing/empty values are not collisions. Messages and reason codes never
include secret values.
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
INSTAGRAM_SIGNING_KEYS = (INSTAGRAM_SIGNING_KEY,)
INSTAGRAM_VERIFY_KEYS = (INSTAGRAM_VERIFY_KEY,)
SIGNING_COLLISION = "instagram_signing_matches_facebook"
VERIFY_COLLISION = "instagram_verify_matches_facebook"
FACEBOOK_SIGNING_ALIAS_MISMATCH = "facebook_signing_aliases_disagree"
FACEBOOK_VERIFY_ALIAS_MISMATCH = "facebook_verify_aliases_disagree"
COLLISION_EXIT = "meta surface secret policy failed"
REPAIR_CONVERGENCE_EXIT = "meta surface secret repair invalid"
CONFIG_COLLISION_KEY = "META_INSTAGRAM_FACEBOOK_SECRET_COLLISION"
RELEASE_ONLY_VERIFY_MODES = frozenset({"cluster-release-only", "local-release-only"})


@dataclass(frozen=True)
class MetaSurfaceSecretSeparation:
    ok: bool
    collisions: tuple[str, ...]


def _normalized_secret(values: Mapping[str, str], key: str) -> str:
    return str(values.get(key) or "").strip().strip("'").strip('"')


def _present_secrets(values: Mapping[str, str], keys: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(secret for key in keys if (secret := _normalized_secret(values, key)))


def _secrets_equal(left: str, right: str) -> bool:
    if not left or not right or len(left) != len(right):
        return False
    return hmac.compare_digest(left, right)


def _facebook_aliases_agree(secrets: tuple[str, ...]) -> bool:
    if len(secrets) < 2:
        return True
    first = secrets[0]
    return all(_secrets_equal(first, other) for other in secrets[1:])


def _cross_surface_collision(left: tuple[str, ...], right: tuple[str, ...]) -> bool:
    return any(_secrets_equal(facebook, instagram) for facebook in left for instagram in right)


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
        *INSTAGRAM_SIGNING_KEYS,
        *INSTAGRAM_VERIFY_KEYS,
    )
    return {key: (os.getenv(key) or "") for key in keys}


def evaluate_meta_surface_secret_separation(
    values: Mapping[str, str],
) -> MetaSurfaceSecretSeparation:
    facebook_signing = _present_secrets(values, FACEBOOK_SIGNING_KEYS)
    facebook_verify = _present_secrets(values, FACEBOOK_VERIFY_KEYS)
    collisions: list[str] = []
    if not _facebook_aliases_agree(facebook_signing):
        collisions.append(FACEBOOK_SIGNING_ALIAS_MISMATCH)
    if not _facebook_aliases_agree(facebook_verify):
        collisions.append(FACEBOOK_VERIFY_ALIAS_MISMATCH)
    if _cross_surface_collision(facebook_signing, _present_secrets(values, INSTAGRAM_SIGNING_KEYS)):
        collisions.append(SIGNING_COLLISION)
    if _cross_surface_collision(facebook_verify, _present_secrets(values, INSTAGRAM_VERIFY_KEYS)):
        collisions.append(VERIFY_COLLISION)
    return MetaSurfaceSecretSeparation(ok=not collisions, collisions=tuple(collisions))


def runtime_meta_surface_secret_separation() -> MetaSurfaceSecretSeparation:
    return evaluate_meta_surface_secret_separation(environ_secret_values())


def require_separated_meta_surface_secrets(values: Mapping[str, str]) -> None:
    result = evaluate_meta_surface_secret_separation(values)
    if not result.ok:
        raise SystemExit(COLLISION_EXIT)


def _authoritative_facebook_value(
    proposed: Mapping[str, str],
    keys: tuple[str, ...],
) -> str | None:
    for key in keys:
        value = _normalized_secret(proposed, key)
        if value:
            return value
    return None


def converge_facebook_surface_secret_updates(
    existing: Mapping[str, str],
    proposed: Mapping[str, str],
) -> dict[str, str]:
    """Mirror any Facebook signing/verify rotation across all active FB aliases."""

    updates = {str(key): str(value) for key, value in proposed.items()}
    new_sign = _authoritative_facebook_value(proposed, FACEBOOK_SIGNING_KEYS)
    if new_sign is not None and any(key in proposed for key in FACEBOOK_SIGNING_KEYS):
        for key in FACEBOOK_SIGNING_KEYS:
            if _normalized_secret(existing, key) or key in proposed:
                updates[key] = new_sign
    elif any(key in proposed for key in FACEBOOK_SIGNING_KEYS):
        raise SystemExit(REPAIR_CONVERGENCE_EXIT)

    new_verify = _authoritative_facebook_value(proposed, FACEBOOK_VERIFY_KEYS)
    if new_verify is not None and any(key in proposed for key in FACEBOOK_VERIFY_KEYS):
        for key in FACEBOOK_VERIFY_KEYS:
            if _normalized_secret(existing, key) or key in proposed:
                updates[key] = new_verify
    elif any(key in proposed for key in FACEBOOK_VERIFY_KEYS):
        raise SystemExit(REPAIR_CONVERGENCE_EXIT)
    return updates


def require_converged_meta_surface_secrets_for_update(
    env_path: Path,
    proposed: Mapping[str, str],
) -> dict[str, str]:
    existing = env_file_values(env_path)
    converged = converge_facebook_surface_secret_updates(existing, proposed)
    merged = dict(existing)
    merged.update(converged)
    require_separated_meta_surface_secrets(merged)
    return converged


def require_separated_meta_surface_secrets_for_update(
    env_path: Path,
    proposed: Mapping[str, str],
) -> None:
    require_converged_meta_surface_secrets_for_update(env_path, proposed)


def operator_gate_allows_separation(
    values: Mapping[str, str],
    *,
    verify_mode: str,
) -> bool:
    if verify_mode in RELEASE_ONLY_VERIFY_MODES:
        return True
    return evaluate_meta_surface_secret_separation(values).ok
