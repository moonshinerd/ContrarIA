"""Marca contas que já receberam o rótulo provavel-bot.

Revision ID: b3a1c9d4e7f2
Revises: 91e7bc852c41
Create Date: 2026-10-05
"""

import sqlalchemy as sa
from alembic import op

revision = "b3a1c9d4e7f2"
down_revision = "91e7bc852c41"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "account_assessments",
        sa.Column("bot_label_applied", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("account_assessments", "bot_label_applied")
