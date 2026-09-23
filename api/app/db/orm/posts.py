
from sqlalchemy import BigInteger, Column, DateTime, String, func
from sqlalchemy.dialects.postgresql import ARRAY

from app.db.base import Base


class Post(Base):
    __tablename__ = "posts"

    uri = Column(String, primary_key=True)
    cid = Column(String, nullable=False)
    author_did = Column(String, nullable=False)
    text = Column(String, nullable=False)
    langs = Column(ARRAY(String), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    source = Column(String, nullable=False)  # 'jetstream' | 'search'
    first_seen_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class IngestCursor(Base):
    __tablename__ = "ingest_cursor"

    stream = Column(String, primary_key=True)
    cursor = Column(BigInteger, nullable=False)
