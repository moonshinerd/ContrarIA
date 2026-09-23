"""Add intervention logs

Revision ID: 3da7ca184e63
Revises: 8a318724f860
Create Date: 2026-09-23 09:21:44.254951
"""

import sqlalchemy as sa
from alembic import op

revision = "3da7ca184e63"
down_revision = "8a318724f860"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "intervention_logs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("post_uri", sa.String(), nullable=False),
        sa.Column("author_did", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_intervention_logs_author_did"), "intervention_logs", ["author_did"], unique=False
    )
    op.create_index(
        op.f("ix_intervention_logs_post_uri"), "intervention_logs", ["post_uri"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_intervention_logs_post_uri"), table_name="intervention_logs")
    op.drop_index(op.f("ix_intervention_logs_author_did"), table_name="intervention_logs")
    op.drop_table("intervention_logs")
