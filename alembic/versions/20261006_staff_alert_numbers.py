"""Per-tenant staff alert numbers.

Revision ID: 20261006_staff_alerts
Revises: 20260920_prod_img_ann
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20261006_staff_alerts"
down_revision: str | None = "20260920_prod_img_ann"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS linas_staff_alert_settings (
            tenant_id TEXT PRIMARY KEY,
            template_name TEXT NOT NULL DEFAULT '',
            template_language TEXT NOT NULL DEFAULT '',
            numbers_json TEXT NOT NULL DEFAULT '[]'
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS linas_staff_alert_settings")
