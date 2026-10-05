from sqlalchemy import JSON, Boolean, Column, DateTime, Float, String, false, func

from app.db.base import Base


class AccountAssessment(Base):
    __tablename__ = "account_assessments"

    did = Column(String, primary_key=True)
    score = Column(Float, nullable=False)
    features = Column(JSON, nullable=False, server_default="{}")
    bot_label_applied = Column(Boolean, nullable=False, server_default=false(), default=False)
    assessed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
