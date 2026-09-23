"""cria tabela de calibração CRC

Revision ID: 5c4f892f79b1
Revises: 4d30889a9e40
Create Date: 2026-09-23
"""

import sqlalchemy as sa
from alembic import op

revision = "5c4f892f79b1"
down_revision = "4d30889a9e40"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "crc_calibration",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("lambda", sa.Float(), nullable=False),
        sa.Column("alpha", sa.Float(), nullable=False),
        sa.Column("n", sa.Integer(), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint('"lambda" >= 0', name="ck_crc_calibration_lambda_nonnegative"),
        sa.CheckConstraint("alpha > 0 AND alpha < 1", name="ck_crc_calibration_alpha_range"),
        sa.CheckConstraint("n > 0", name="ck_crc_calibration_n_positive"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_crc_calibration_model", "crc_calibration", ["model"], unique=False)
    op.create_index(
        "ix_crc_calibration_created_at", "crc_calibration", ["created_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_crc_calibration_created_at", table_name="crc_calibration")
    op.drop_index("ix_crc_calibration_model", table_name="crc_calibration")
    op.drop_table("crc_calibration")
