"""Durable CM ops flags that must survive normal production deploys/restarts.

``CM_DISABLE_LINAS_LEGACY_BRIDGE`` lives in the systemd ``EnvironmentFile`` ``.env``
(not in git). Deploy rewrites the unit file but must not lose this key.
Emergency rollback remains ``CM_EMERGENCY_FORCE_LEGACY=true`` (separate flag).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


CM_DISABLE_LINAS_LEGACY_BRIDGE = "CM_DISABLE_LINAS_LEGACY_BRIDGE"
CM_EMERGENCY_FORCE_LEGACY = "CM_EMERGENCY_FORCE_LEGACY"

_TRUTHY = {"1", "true", "yes"}
_FALSY = {"0", "false", "no"}


def default_production_env_paths(*, app_dir: str | Path | None = None) -> list[Path]:
    """Paths that may hold durable flags on the production host."""
    repo_root = Path("/opt/linasbot")
    nested = repo_root / "linaslaserbot-2.7.22"
    paths: list[Path] = []
    if app_dir is not None:
        paths.append(Path(app_dir) / ".env")
    paths.extend(
        [
            repo_root / ".env",
            nested / ".env",
        ]
    )
    # Preserve order, drop duplicates, keep only parents that exist (or will be created for app_dir).
    seen: set[str] = set()
    out: list[Path] = []
    for path in paths:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        if path.parent.exists() or (app_dir is not None and path.parent == Path(app_dir)):
            out.append(path)
    return out


def parse_env_bool(raw: str | None) -> bool | None:
    if raw is None:
        return None
    text = raw.strip().strip("'").strip('"').lower()
    if text in _TRUTHY:
        return True
    if text in _FALSY:
        return False
    if text == "":
        return None
    return None


def read_env_file_map(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        key, value = s.split("=", 1)
        key = key.strip()
        if key:
            out[key] = value.strip().strip("'").strip('"')
    return out


def upsert_env_file(path: Path, updates: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    found: set[str] = set()
    out: list[str] = []
    for line in lines:
        if "=" in line and not line.lstrip().startswith("#"):
            key = line.split("=", 1)[0].strip()
            if key in updates:
                out.append(f"{key}={updates[key]}")
                found.add(key)
                continue
        out.append(line)
    for key, value in updates.items():
        if key not in found:
            out.append(f"{key}={value}")
    path.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
    os.chmod(path, 0o600)


def resolve_disable_bridge_value(
    present_values: list[bool | None],
    *,
    linas_has_published_cm: bool,
) -> tuple[bool | None, str]:
    """Choose durable value for ``CM_DISABLE_LINAS_LEGACY_BRIDGE``.

    Returns ``(value_or_None_if_unset, reason)``.
    """
    if any(v is True for v in present_values):
        return True, "preserve_true_from_existing_env"
    if any(v is False for v in present_values):
        return False, "preserve_explicit_false"
    if linas_has_published_cm:
        # Recover from deploy dual-path / missing-key wipe after Linas published cutover.
        return True, "recover_true_for_published_linas"
    return None, "unset_ok_no_published_linas"


def preserve_disable_linas_legacy_bridge(
    env_paths: list[Path],
    *,
    linas_has_published_cm: bool,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Sync/preserve the bridge-disable flag across production ``.env`` files."""
    snapshots: list[dict[str, Any]] = []
    values: list[bool | None] = []
    for path in env_paths:
        mapping = read_env_file_map(path)
        raw = mapping.get(CM_DISABLE_LINAS_LEGACY_BRIDGE)
        parsed = parse_env_bool(raw)
        values.append(parsed)
        snapshots.append(
            {
                "path": str(path),
                "exists": path.is_file(),
                "raw_present": CM_DISABLE_LINAS_LEGACY_BRIDGE in mapping,
                "parsed": parsed,
            }
        )

    effective, reason = resolve_disable_bridge_value(
        values, linas_has_published_cm=linas_has_published_cm
    )
    report: dict[str, Any] = {
        "key": CM_DISABLE_LINAS_LEGACY_BRIDGE,
        "paths": snapshots,
        "linas_has_published_cm": linas_has_published_cm,
        "effective": effective,
        "reason": reason,
        "dry_run": dry_run,
        "updated_paths": [],
        "ok": True,
        "failures": [],
    }

    if effective is None:
        if linas_has_published_cm:
            report["ok"] = False
            report["failures"].append("published_linas_missing_disable_bridge_flag")
        return report

    desired = "true" if effective else "false"
    if not dry_run:
        for path in env_paths:
            if not path.parent.exists():
                continue
            upsert_env_file(path, {CM_DISABLE_LINAS_LEGACY_BRIDGE: desired})
            report["updated_paths"].append(str(path))

    # Post-condition: every written/existing file must parse to effective.
    for path in env_paths:
        if dry_run or not path.is_file():
            continue
        got = parse_env_bool(read_env_file_map(path).get(CM_DISABLE_LINAS_LEGACY_BRIDGE))
        if got != effective:
            report["ok"] = False
            report["failures"].append(f"path_mismatch:{path}")

    if linas_has_published_cm and effective is not True:
        report["ok"] = False
        report["failures"].append("published_linas_requires_disable_bridge_true")

    return report


def readiness_requires_disable_bridge(
    *,
    linas_has_published_cm: bool,
    effective_disable_bridge: bool | None,
) -> dict[str, Any]:
    """Fail closed when Linas is published-only but the durable disable flag would be lost."""
    ok = True
    failures: list[str] = []
    if linas_has_published_cm and effective_disable_bridge is not True:
        ok = False
        failures.append("linas_published_but_cm_disable_linas_legacy_bridge_not_true")
    return {
        "ok": ok,
        "failures": failures,
        "linas_has_published_cm": linas_has_published_cm,
        "effective_disable_bridge": effective_disable_bridge,
        "emergency_rollback_flag": CM_EMERGENCY_FORCE_LEGACY,
        "note": (
            f"Set {CM_EMERGENCY_FORCE_LEGACY}=true for emergency legacy rollback; "
            f"keep {CM_DISABLE_LINAS_LEGACY_BRIDGE}=true so normal deploys stay on published CM."
        ),
    }
