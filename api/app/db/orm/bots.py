from sqlalchemy import Column, DateTime, Float, String, func, JSON

from app.db.base import Base

class AccountAssessment(Base):
    __tablename__ = "account_assessments"

    did = Column(String, primary_key=True)
    score = Column(Float, nullable=False)
    features = Column(JSON, nullable=False, server_default='{}')
    assessed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
