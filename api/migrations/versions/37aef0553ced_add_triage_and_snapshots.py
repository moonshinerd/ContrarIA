"""Add triage and snapshots

Revision ID: 37aef0553ced
Revises: 7f960ab77012
Create Date: 2026-09-23 09:03:14.247090
"""

import sqlalchemy as sa
from alembic import op

revision = "37aef0553ced"
down_revision = "7f960ab77012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("posts", sa.Column("triage_status", sa.String(), nullable=True))
    op.add_column("posts", sa.Column("priority", sa.Float(), nullable=True))
    op.create_table(
        "post_engagement_snapshots",
        sa.Column("uri", sa.String(), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("likes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("reposts", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("replies", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("quotes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("uri", "ts"),
    )


def downgrade() -> None:
    op.drop_table("post_engagement_snapshots")
    op.drop_column("posts", "priority")
    op.drop_column("posts", "triage_status")
