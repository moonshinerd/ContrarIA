"""create llm_usage table

Revision ID: 175ce9602c45
Revises:
Create Date: 2026-09-21 10:11:46.889372
"""

import sqlalchemy as sa
from alembic import op

revision = "175ce9602c45"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "llm_usage",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("purpose", sa.String(), nullable=False),
        sa.Column("tokens_in", sa.Integer(), server_default="0", nullable=False),
        sa.Column("tokens_out", sa.Integer(), server_default="0", nullable=False),
        sa.Column("cost_usd", sa.Float(), server_default="0.0", nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_llm_usage_date"), "llm_usage", ["date"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_llm_usage_date"), table_name="llm_usage")
    op.drop_table("llm_usage")
