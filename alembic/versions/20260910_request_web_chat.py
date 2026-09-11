"""Allow Website Chat as a customer-request source channel.

Revision ID: 20260910_req_web_chat
Revises: 20260910_msg_billing

SOURCE_CHANNELS already included web_chat. The row check did not, so Brain
persist remapped Website Chat to Instagram. Do not invent TikTok as a source.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260910_req_web_chat"
down_revision: str | None = "20260910_msg_billing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_WITH_WEB = (
    "source_channel IN ("
    "'instagram_dm','facebook_messenger',"
    "'whatsapp_cloud','comment_linked_dm','web_chat')"
)
_WITHOUT_WEB = (
    "source_channel IN ("
    "'instagram_dm','facebook_messenger',"
    "'whatsapp_cloud','comment_linked_dm')"
)


def upgrade() -> None:
    op.drop_constraint("ck_customer_requests_channel", "customer_requests", type_="check")
    op.create_check_constraint("ck_customer_requests_channel", "customer_requests", _WITH_WEB)


def downgrade() -> None:
    op.drop_constraint("ck_customer_requests_channel", "customer_requests", type_="check")
    op.create_check_constraint("ck_customer_requests_channel", "customer_requests", _WITHOUT_WEB)
