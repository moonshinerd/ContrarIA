"""Add account assessments cache

Revision ID: ca716cfcc60f
Revises: 37aef0553ced
Create Date: 2026-09-23 09:10:13.429251
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "ca716cfcc60f"
down_revision = "37aef0553ced"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "account_assessments",
        sa.Column("did", sa.String(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("features", JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "assessed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("did"),
    )


def downgrade() -> None:
    op.drop_table("account_assessments")
