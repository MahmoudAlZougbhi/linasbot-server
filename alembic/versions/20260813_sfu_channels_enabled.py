"""Add per-channel enable flags to Smart Follow-Up settings."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "20260813_sfu_channels_enabled"
down_revision: str | None = "20260813_smart_followup_channels"
branch_labels = None
depends_on = None

_DEFAULT_CHANNELS = (
    '{"whatsapp_cloud": true, "instagram_dm": true, "facebook_messenger": true}'
)


def upgrade() -> None:
    op.add_column(
        "whatsapp_smart_followup_settings",
        sa.Column("channels_enabled", sa.JSON(), nullable=False, server_default=_DEFAULT_CHANNELS),
    )


def downgrade() -> None:
    op.drop_column("whatsapp_smart_followup_settings", "channels_enabled")
