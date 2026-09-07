"""Per-tenant watchlist of posts that should receive comment AI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from storage.persistent_storage import get_data_root

Platform = Literal["instagram", "facebook", "tiktok"]
Mode = Literal["all", "selected"]
PLATFORMS = frozenset({"instagram", "facebook", "tiktok"})


def _path(tenant_id: str) -> Path:
    return Path(get_data_root()) / "tenants" / str(tenant_id or "").strip() / "comments_inbox" / "watchlist.json"


def _empty_platform() -> dict[str, Any]:
    return {"mode": "all", "post_ids": []}


def load_watchlist(tenant_id: str) -> dict[str, dict[str, Any]]:
    path = _path(tenant_id)
    raw: dict[str, Any] = {}
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            loaded = {}
        if isinstance(loaded, dict):
            raw = loaded
    out: dict[str, dict[str, Any]] = {}
    for platform in PLATFORMS:
        candidate = raw.get(platform)
        row = candidate if isinstance(candidate, dict) else {}
        mode = str(row.get("mode") or "all").strip().lower()
        ids = [str(item).strip() for item in (row.get("post_ids") or []) if str(item).strip()]
        out[platform] = {"mode": "selected" if mode == "selected" else "all", "post_ids": ids}
    return out


def save_watchlist(tenant_id: str, payload: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    cleaned = load_watchlist(tenant_id)
    for platform, row in payload.items():
        if platform not in PLATFORMS or not isinstance(row, dict):
            continue
        mode = str(row.get("mode") or cleaned[platform]["mode"]).strip().lower()
        ids = [str(item).strip() for item in (row.get("post_ids") or []) if str(item).strip()]
        cleaned[platform] = {
            "mode": "selected" if mode == "selected" else "all",
            "post_ids": list(dict.fromkeys(ids)),
        }
    path = _path(tenant_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2), encoding="utf-8")
    return cleaned


def platform_watch(tenant_id: str, platform: str) -> dict[str, Any]:
    plat = str(platform or "").strip().lower()
    if plat not in PLATFORMS:
        return _empty_platform()
    return load_watchlist(tenant_id).get(plat) or _empty_platform()


def comment_post_allowed(tenant_id: str, platform: str, post_id: str) -> bool:
    """True when comment AI may run on this post. Empty/all = current behavior."""
    watch = platform_watch(tenant_id, platform)
    if str(watch.get("mode") or "all") != "selected":
        return True
    want = str(post_id or "").strip()
    if not want:
        return False
    return want in {str(item) for item in (watch.get("post_ids") or [])}


def apply_watch_patch(
    tenant_id: str,
    *,
    platform: str,
    mode: str | None = None,
    post_id: str = "",
    selected: bool | None = None,
    known_ids: list[str] | None = None,
    post_ids: list[str] | None = None,
) -> dict[str, Any]:
    plat = str(platform or "").strip().lower()
    if plat not in PLATFORMS:
        raise ValueError("unknown_platform")
    current = load_watchlist(tenant_id)
    row = dict(current.get(plat) or _empty_platform())
    if mode in {"all", "selected"}:
        row["mode"] = mode
        if mode == "all":
            row["post_ids"] = []
    if post_ids is not None:
        row["mode"] = "selected"
        row["post_ids"] = [str(item).strip() for item in post_ids if str(item).strip()]
    want = str(post_id or "").strip()
    if want and selected is not None:
        ids = list(row.get("post_ids") or [])
        if str(row.get("mode") or "all") != "selected":
            if selected:
                return current.get(plat) or _empty_platform()
            row["mode"] = "selected"
            ids = [str(item).strip() for item in (known_ids or []) if str(item).strip() and item != want]
        elif selected and want not in ids:
            ids.append(want)
        elif not selected:
            ids = [item for item in ids if item != want]
        row["post_ids"] = list(dict.fromkeys(ids))
    current[plat] = row
    saved = save_watchlist(tenant_id, current)
    return saved[plat]
