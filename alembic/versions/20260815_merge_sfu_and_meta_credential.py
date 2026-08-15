"""No-op merge of Smart Follow-Up and Meta credential archive heads.

Revision ID: 20260815_merge_sfu_and_meta_credential
Revises: 20260813_sfu_channels_enabled, 20260814_meta_credential_archived_at
Create Date: 2026-08-15

Schema no-op. Makes Alembic metadata a single head. This revision must not be
applied to production as part of the code-only audit fix; live migrate only
after a separate owner-approved cutover.
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "20260815_merge_sfu_and_meta_credential"
down_revision: tuple[str, str] = (
    "20260813_sfu_channels_enabled",
    "20260814_meta_credential_archived_at",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
