"""
Version tracking for text handlers module
Update this file whenever you make changes to ensure you're running the latest version
"""

from __future__ import annotations

import datetime
from typing import Any

# Increment this with each deployment
VERSION = "2.1.0"

# Update this timestamp when deploying
LAST_MODIFIED = "2025-01-24 22:00:00"

# Change this ID to identify specific builds
BUILD_ID = "NAME_COLLECTION_v1"

# Deployment notes
CHANGES = """
v2.1.0 - 2025-01-24
- ✅ ADDED: Proactive name collection after gender confirmation
- Bot now asks for name immediately after gender is confirmed
- Name is validated (2-50 chars, letters only)
- Name is saved to memory and Firestore
- Bot uses the name in all future interactions

v2.0.0 - 2025-01-24
- Split text_handlers.py into 5 modular files
- Prevents file corruption during edits
- Better organization and maintainability
"""


def print_version_info() -> None:
    """No-op kept for backward compatibility with text_handlers import."""
    return


def get_version() -> Any:
    """Return version string"""
    return VERSION


def get_build_info() -> Any:
    """Return complete build information"""
    return {
        "version": VERSION,
        "build_id": BUILD_ID,
        "last_modified": LAST_MODIFIED,
        "loaded_at": datetime.datetime.now().isoformat(),
        "changes": CHANGES,
    }
