# -*- coding: utf-8 -*-
"""
Persistent Storage - Central configuration for dashboard-managed data.
All runtime-managed data lives under LINASBOT_DATA_ROOT (default: /opt/linasbot_data).
This prevents data loss on deploy/rebuild when project directory is replaced.
"""

import os
import shutil
from pathlib import Path

# Root for persistent data. Override with LINASBOT_DATA_ROOT env var.
_LINASBOT_DATA_ROOT = os.getenv("LINASBOT_DATA_ROOT", "/opt/linasbot_data")
_DATA_ROOT = Path(_LINASBOT_DATA_ROOT)

# Legacy project data dir (relative to project root)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_LEGACY_DATA = _PROJECT_ROOT / "data"

# --- Paths (all under LINASBOT_DATA_ROOT) ---

QA_DIR = _DATA_ROOT / "qa"
CONTENT_DIR = _DATA_ROOT / "content"
SETTINGS_DIR = _DATA_ROOT / "settings"
SMART_MESSAGING_DIR = _DATA_ROOT / "smart_messaging"

# QA
QA_PAIRS_FILE = QA_DIR / "qa_pairs.jsonl"
QA_DATABASE_FILE = QA_DIR / "qa_database.json"

# Content - legacy single files + multi-file sections
KNOWLEDGE_BASE_FILE = CONTENT_DIR / "knowledge_base.txt"
STYLE_GUIDE_FILE = CONTENT_DIR / "style_guide.txt"
PRICE_LIST_FILE = CONTENT_DIR / "price_list.txt"
KNOWLEDGE_FILES_DIR = CONTENT_DIR / "knowledge_files"
STYLE_FILES_DIR = CONTENT_DIR / "style_files"
PRICE_FILES_DIR = CONTENT_DIR / "price_files"

# Settings
APP_SETTINGS_FILE = SETTINGS_DIR / "app_settings.json"

# Logs (Activity Flow, etc. – survives deploy)
LOGS_DIR = _DATA_ROOT / "logs"
ACTIVITY_FLOW_FILE = LOGS_DIR / "activity_flow.jsonl"

# Smart Messaging
MESSAGE_TEMPLATES_FILE = SMART_MESSAGING_DIR / "message_templates.json"
MESSAGE_TEMPLATES_LOCK_FILE = SMART_MESSAGING_DIR / ".message_templates.lock"
SENT_SMART_MESSAGES_FILE = SMART_MESSAGING_DIR / "sent_smart_messages.json"
SERVICE_TEMPLATE_MAPPING_FILE = SMART_MESSAGING_DIR / "service_template_mapping.json"
MESSAGE_PREVIEW_QUEUE_FILE = SMART_MESSAGING_DIR / "message_preview_queue.json"
DAILY_TEMPLATE_DISPATCH_STATE_FILE = SMART_MESSAGING_DIR / "daily_template_dispatch_state.json"
MESSAGE_QUEUE_FILE = SMART_MESSAGING_DIR / "message_queue.json"
APPOINTMENT_FINGERPRINTS_FILE = SMART_MESSAGING_DIR / "appointment_fingerprints.json"
TEMPLATE_ACTIVATION_STATUS_FILE = SMART_MESSAGING_DIR / "template_activation_status.json"
SCHEDULED_MESSAGES_FILE = SMART_MESSAGING_DIR / "scheduled_messages_to_be_sent.json"
DRY_RUN_MESSAGES_FILE = SMART_MESSAGING_DIR / "dry_run_messages.jsonl"


def get_qa_path(relative: str) -> Path:
    """Get path under qa/."""
    return QA_DIR / relative


def get_content_path(relative: str) -> Path:
    """Get path under content/."""
    return CONTENT_DIR / relative


def get_settings_path(relative: str) -> Path:
    """Get path under settings/."""
    return SETTINGS_DIR / relative


def get_smart_messaging_path(relative: str) -> Path:
    """Get path under smart_messaging/."""
    return SMART_MESSAGING_DIR / relative


def ensure_dirs():
    """Create all persistent data directories."""
    for d in (QA_DIR, CONTENT_DIR, SETTINGS_DIR, SMART_MESSAGING_DIR, LOGS_DIR,
              KNOWLEDGE_FILES_DIR, STYLE_FILES_DIR, PRICE_FILES_DIR):
        d.mkdir(parents=True, exist_ok=True)


def _safe_migrate_file(legacy_path: Path, new_path: Path, *, overwrite: bool = False) -> bool:
    """
    Migrate a single file from legacy project dir to persistent dir.
    Do NOT overwrite existing production data unless overwrite=True.
    Returns True if migration was performed.
    """
    if not legacy_path.exists():
        return False
    if new_path.exists() and not overwrite:
        return False  # Production data exists - keep it
    try:
        new_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(legacy_path, new_path)
        print(f"  ✅ Migrated {legacy_path.name} → {new_path}")
        return True
    except Exception as e:
        print(f"  ⚠️ Migration failed for {legacy_path}: {e}")
        return False


def _safe_migrate_dir(legacy_dir: Path, new_dir: Path, *, overwrite_files: bool = False) -> bool:
    """
    Migrate a directory. For each file in legacy: copy if new doesn't exist.
    Returns True if any file was migrated.
    """
    if not legacy_dir.exists() or not legacy_dir.is_dir():
        return False
    migrated = False
    for name in os.listdir(legacy_dir):
        src = legacy_dir / name
        dst = new_dir / name
        if src.is_file():
            if dst.exists() and not overwrite_files:
                continue
            try:
                new_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                print(f"  ✅ Migrated {src.relative_to(legacy_dir)} → {dst}")
                migrated = True
            except Exception as e:
                print(f"  ⚠️ Migration failed for {src}: {e}")
    return migrated


def migrate_from_legacy():
    """
    Safe one-time migration: move data from project data/ to persistent dir.
    - Only migrates if legacy file exists and new file does NOT exist.
    - Never overwrites existing production data.
    """
    ensure_dirs()
    migrated_any = False

    # QA
    if _safe_migrate_file(_LEGACY_DATA / "qa_pairs.jsonl", QA_PAIRS_FILE):
        migrated_any = True
    if _safe_migrate_file(_LEGACY_DATA / "qa_database.json", QA_DATABASE_FILE):
        migrated_any = True

    # Content - legacy single files
    if _safe_migrate_file(_LEGACY_DATA / "knowledge_base.txt", KNOWLEDGE_BASE_FILE):
        migrated_any = True
    if _safe_migrate_file(_LEGACY_DATA / "style_guide.txt", STYLE_GUIDE_FILE):
        migrated_any = True
    if _safe_migrate_file(_LEGACY_DATA / "price_list.txt", PRICE_LIST_FILE):
        migrated_any = True

    # Content - multi-file sections
    if _safe_migrate_dir(_LEGACY_DATA / "knowledge_files", KNOWLEDGE_FILES_DIR):
        migrated_any = True
    if _safe_migrate_dir(_LEGACY_DATA / "style_files", STYLE_FILES_DIR):
        migrated_any = True
    if _safe_migrate_dir(_LEGACY_DATA / "price_files", PRICE_FILES_DIR):
        migrated_any = True

    # Content - backups (style_guide_backup_*, etc.)
    if _LEGACY_DATA.exists():
        for f in _LEGACY_DATA.iterdir():
            if f.is_file() and ("backup" in f.name.lower() or "backup_before_restore" in f.name.lower()):
                if _safe_migrate_file(f, CONTENT_DIR / f.name):
                    migrated_any = True

    # Settings
    if _safe_migrate_file(_LEGACY_DATA / "app_settings.json", APP_SETTINGS_FILE):
        migrated_any = True

    # Logs (Activity Flow)
    if _safe_migrate_file(_LEGACY_DATA / "activity_flow.jsonl", ACTIVITY_FLOW_FILE):
        migrated_any = True

    # Smart messaging
    for fname in ("message_templates.json", "sent_smart_messages.json", "service_template_mapping.json",
                  "message_preview_queue.json", "daily_template_dispatch_state.json", "message_queue.json",
                  "appointment_fingerprints.json", "template_activation_status.json",
                  "scheduled_messages_to_be_sent.json", "dry_run_messages.jsonl"):
        if _safe_migrate_file(_LEGACY_DATA / fname, SMART_MESSAGING_DIR / fname):
            migrated_any = True

    if migrated_any:
        print("📦 Persistent storage migration completed. Data now in " + str(_DATA_ROOT))
    return migrated_any


def get_data_root() -> Path:
    """Return the persistent data root path."""
    return _DATA_ROOT


def get_legacy_data_dir() -> Path:
    """Return the legacy project data dir (for reference only)."""
    return _LEGACY_DATA
