"""Stage live LINASBOT_DATA_ROOT content into fixture-shaped legacy/ for CM migration."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any


def resolve_live_data_root(explicit: str | Path | None = None) -> Path:
    if explicit:
        root = Path(explicit)
        if not root.is_dir():
            raise FileNotFoundError(f"Data root not found: {root}")
        return root
    from storage.persistent_storage import get_data_root

    return Path(get_data_root())


def stage_live_data_for_migration(
    *,
    data_root: Path,
    staging_root: Path,
    app_data_root: Path | None = None,
) -> dict[str, Any]:
    """Copy live FAQ/content into ``staging_root/legacy/`` for migrate_legacy_fixture."""
    legacy = staging_root / "legacy"
    if staging_root.exists():
        shutil.rmtree(staging_root)
    legacy.mkdir(parents=True, exist_ok=True)
    (legacy / "knowledge_files").mkdir(parents=True, exist_ok=True)
    (legacy / "style_files").mkdir(parents=True, exist_ok=True)

    copied: list[dict[str, str]] = []
    missing: list[str] = []

    def _copy(src: Path, dest: Path) -> None:
        if not src.exists():
            missing.append(str(src))
            return
        dest.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(src, dest)
        else:
            shutil.copy2(src, dest)
        copied.append({"src": str(src), "dest": str(dest)})

    # Prefer persistent layout; also accept flat project data/ for recovery copies.
    # Production historically keeps FAQ/content under /opt/linasbot/data as well as LINASBOT_DATA_ROOT.
    app_data = Path(app_data_root) if app_data_root is not None else Path("/opt/linasbot/data")
    candidates = {
        "qa_pairs.jsonl": [
            data_root / "qa" / "qa_pairs.jsonl",
            data_root / "qa_pairs.jsonl",
            app_data / "qa" / "qa_pairs.jsonl",
            app_data / "qa_pairs.jsonl",
        ],
        "price_list.txt": [
            data_root / "content" / "price_list.txt",
            data_root / "price_list.txt",
            app_data / "price_list.txt",
            app_data / "content" / "price_list.txt",
        ],
        "knowledge_base.txt": [
            data_root / "content" / "knowledge_base.txt",
            data_root / "knowledge_base.txt",
            app_data / "knowledge_base.txt",
            app_data / "content" / "knowledge_base.txt",
        ],
        "style_guide.txt": [
            data_root / "content" / "style_guide.txt",
            data_root / "style_guide.txt",
            app_data / "style_guide.txt",
            app_data / "content" / "style_guide.txt",
        ],
        "system_prompt_template.txt": [
            data_root / "content" / "system_prompt_template.txt",
            data_root / "system_prompt_template.txt",
            app_data / "system_prompt_template.txt",
            app_data / "content" / "system_prompt_template.txt",
        ],
    }
    for name, paths in candidates.items():
        # Prefer the first *non-empty* existing candidate so an empty placeholder under
        # LINASBOT_DATA_ROOT cannot shadow the live /opt/linasbot/data copy.
        existing = [p for p in paths if p.exists()]
        chosen = next((p for p in existing if p.is_file() and p.stat().st_size > 0), None)
        if chosen is None and existing:
            chosen = existing[0]
        if chosen is None:
            missing.append(name)
            continue
        _copy(chosen, legacy / name)

    for kf_root in (
        data_root / "content" / "knowledge_files",
        data_root / "knowledge_files",
        app_data / "knowledge_files",
        app_data / "content" / "knowledge_files",
    ):
        if kf_root.is_dir():
            for path in sorted(kf_root.glob("*.json")):
                _copy(path, legacy / "knowledge_files" / path.name)

    for sf_root in (
        data_root / "content" / "style_files",
        data_root / "style_files",
        app_data / "style_files",
        app_data / "content" / "style_files",
    ):
        if sf_root.is_dir():
            for path in sorted(sf_root.iterdir()):
                if path.is_file():
                    _copy(path, legacy / "style_files" / path.name)

    for pf_root in (
        data_root / "content" / "price_files",
        data_root / "price_files",
        app_data / "price_files",
        app_data / "content" / "price_files",
    ):
        if pf_root.is_dir():
            dest_dir = legacy / "price_files"
            dest_dir.mkdir(parents=True, exist_ok=True)
            for path in sorted(pf_root.glob("*.json")):
                _copy(path, dest_dir / path.name)

    dyn_candidates = [
        data_root / "settings" / "dynamic_messages.json",
        data_root / "dynamic_messages.json",
        app_data / "settings" / "dynamic_messages.json",
        app_data / "dynamic_messages.json",
    ]
    dyn_src = next((p for p in dyn_candidates if p.exists() and p.is_file() and p.stat().st_size > 0), None)
    if dyn_src is None:
        dyn_src = next((p for p in dyn_candidates if p.exists()), None)
    if dyn_src is not None:
        _copy(dyn_src, legacy / "dynamic_messages.json")

    settings_candidates = [
        data_root / "settings" / "app_settings.json",
        data_root / "app_settings.json",
        app_data / "settings" / "app_settings.json",
        app_data / "app_settings.json",
    ]
    settings_src = next((p for p in settings_candidates if p.exists()), None)
    if settings_src is not None:
        _copy(settings_src, legacy / "app_settings.json")

    manifest = {
        "schema": "cm_prod_stage_v1",
        "data_root": str(data_root),
        "app_data_root": str(app_data),
        "copied": copied,
        "missing": missing,
    }
    (staging_root / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return manifest
