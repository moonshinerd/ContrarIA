"""Cria a outbox de rótulos do Ozone (label_events).

Revision ID: 0003_create_label_events
Revises: 0002_create_system_logs
Create Date: 2026-10-07
"""

import sqlalchemy as sa
from alembic import op

revision = "0003_create_label_events"
down_revision = "0002_create_system_logs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "label_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("subject_kind", sa.String(10), nullable=False),
        sa.Column("subject_uri", sa.String(), nullable=False),
        sa.Column("subject_cid", sa.String(), nullable=True),
        sa.Column("label_val", sa.String(64), nullable=False),
        sa.Column("action", sa.String(10), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_label_events_subject_uri", "label_events", ["subject_uri"])
    op.create_index("ix_label_events_status", "label_events", ["status"])
    op.create_index("ix_label_events_status_next", "label_events", ["status", "next_attempt_at"])


def downgrade() -> None:
    op.drop_index("ix_label_events_status_next", table_name="label_events")
    op.drop_index("ix_label_events_status", table_name="label_events")
    op.drop_index("ix_label_events_subject_uri", table_name="label_events")
    op.drop_table("label_events")
