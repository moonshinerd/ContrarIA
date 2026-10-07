"""Cria tabela system_logs para armazenamento de logs do sistema.

Revision ID: 0002_create_system_logs
Revises: b3a1c9d4e7f2
Create Date: 2026-10-07
"""

import sqlalchemy as sa
from alembic import op

revision = "0002_create_system_logs"
down_revision = "b3a1c9d4e7f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "system_logs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("level", sa.String(length=20), nullable=False),
        sa.Column("logger", sa.String(length=100), nullable=False),
        sa.Column("service", sa.String(length=50), nullable=False, server_default="unknown"),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("context", sa.JSON(), nullable=True),
    )
    op.create_index("ix_system_logs_created_at", "system_logs", ["created_at"])
    op.create_index("ix_system_logs_level", "system_logs", ["level"])
    op.create_index("ix_system_logs_logger", "system_logs", ["logger"])
    op.create_index("ix_system_logs_service", "system_logs", ["service"])
    op.create_index("ix_system_logs_service_created", "system_logs", ["service", "created_at"])
    op.create_index("ix_system_logs_level_created", "system_logs", ["level", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_system_logs_level_created", table_name="system_logs")
    op.drop_index("ix_system_logs_service_created", table_name="system_logs")
    op.drop_index("ix_system_logs_service", table_name="system_logs")
    op.drop_index("ix_system_logs_logger", table_name="system_logs")
    op.drop_index("ix_system_logs_level", table_name="system_logs")
    op.drop_index("ix_system_logs_created_at", table_name="system_logs")
    op.drop_table("system_logs")
