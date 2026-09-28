"""Acervo RSS com pgvector (issue #21)."""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision = "0001_fact_articles"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "fact_articles",
        sa.Column("url", sa.Text(), primary_key=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("embedding", Vector(384), nullable=False),
    )
    op.create_index("ix_fact_articles_source", "fact_articles", ["source"])


def downgrade():
    op.drop_table("fact_articles")
