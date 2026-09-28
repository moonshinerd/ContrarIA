"""Add immutable decision log and review events.

Revision ID: 91e7bc852c41
Revises: 3da7ca184e63
Create Date: 2026-09-23
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "91e7bc852c41"
down_revision = "3da7ca184e63"
branch_labels = None
depends_on = None


def upgrade() -> None:
    json_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
    op.create_table(
        "decisions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("post_uri", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("post_snapshot", json_type, nullable=False),
        sa.Column("bot_score", sa.Float(), nullable=True),
        sa.Column("bot_features", json_type, nullable=True),
        sa.Column("sources", json_type, nullable=True),
        sa.Column("agent_outputs", json_type, nullable=True),
        sa.Column("verdict", sa.String(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("crc_threshold_used", sa.Float(), nullable=True),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("justification", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_decisions_post_uri"), "decisions", ["post_uri"], unique=False)
    op.create_table(
        "decision_reviews",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("decision_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("justification", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["decision_id"], ["decisions.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_decision_reviews_decision_id"), "decision_reviews", ["decision_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_decision_reviews_decision_id"), table_name="decision_reviews")
    op.drop_table("decision_reviews")
    op.drop_index(op.f("ix_decisions_post_uri"), table_name="decisions")
    op.drop_table("decisions")
