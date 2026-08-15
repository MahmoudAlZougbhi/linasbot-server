"""Widen alembic_version.version_num before any revision id longer than 32.

Revision ID: 20260814_widen_ver_num
Revises: 20260812_meta_app_registry
Create Date: 2026-08-14

Alembic 1.14 creates alembic_version.version_num as VARCHAR(32). The next
revision id is 36 characters, so this short-id step must run first.

Live production already stores VARCHAR(64) and has stamped
20260814_meta_credential_archived_at. This ancestor is not re-run for that
head; do not apply this branch on live as part of the code-only fix.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260814_widen_ver_num"
down_revision: str | None = "20260812_meta_app_registry"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_WIDE = 64
_DEFAULT = 32


def upgrade() -> None:
    op.execute(sa.text(f"ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR({_WIDE})"))


def downgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT version_num FROM alembic_version")).fetchall()
    if any(row[0] is not None and len(str(row[0])) > _DEFAULT for row in rows):
        raise RuntimeError("cannot shrink alembic_version.version_num while a long revision is stamped")
    op.execute(sa.text(f"ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR({_DEFAULT})"))
