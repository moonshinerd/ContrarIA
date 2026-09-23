from sqlalchemy import BigInteger, Column, DateTime, Float, String, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy import JSON

from app.db.base import Base


class Post(Base):
    __tablename__ = "posts"

    uri = Column(String, primary_key=True)
    cid = Column(String, nullable=False)
    author_did = Column(String, nullable=False)
    text = Column(String, nullable=False)
    langs = Column(JSON().with_variant(ARRAY(String), "postgresql"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    source = Column(String, nullable=False)  # 'jetstream' | 'search'
    first_seen_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    triage_status = Column(String, nullable=True)  # 'monitor' | 'queued' | 'discarded'
    priority = Column(Float, nullable=True)


class PostEngagementSnapshot(Base):
    __tablename__ = "post_engagement_snapshots"

    uri = Column(String, primary_key=True)
    ts = Column(DateTime(timezone=True), primary_key=True)
    likes = Column(BigInteger, nullable=False, default=0)
    reposts = Column(BigInteger, nullable=False, default=0)
    replies = Column(BigInteger, nullable=False, default=0)
    quotes = Column(BigInteger, nullable=False, default=0)


class IngestCursor(Base):
    __tablename__ = "ingest_cursor"

    stream = Column(String, primary_key=True)
    cursor = Column(BigInteger, nullable=False)
