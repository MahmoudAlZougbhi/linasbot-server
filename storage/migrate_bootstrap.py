"""Side-effect import: run legacy data migration before other app imports."""

from __future__ import annotations

from storage.persistent_storage import migrate_from_legacy

migrate_from_legacy()
MIGRATED = True
