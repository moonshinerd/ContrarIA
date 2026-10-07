"""Outbox de rótulos do Ozone: cada emissão fica registrada e pode ser repetida."""

from sqlalchemy import BigInteger, Column, DateTime, Index, Integer, String, Text, func
from sqlalchemy.types import Integer as SAInteger

from app.db.base import Base


class LabelEvent(Base):
    """Pedido de emissão (ou negação) de um rótulo, com o estado da entrega ao Ozone.

    `status`: `pending` (a enviar ou a repetir), `sent` (o Ozone aceitou) ou `failed`
    (esgotou as tentativas; só reaparece à mão).
    """

    __tablename__ = "label_events"
    __table_args__ = (Index("ix_label_events_status_next", "status", "next_attempt_at"),)

    id = Column(
        BigInteger().with_variant(SAInteger, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    subject_kind = Column(String(10), nullable=False)  # 'post' | 'account'
    subject_uri = Column(String, nullable=False, index=True)  # URI do post ou DID da conta
    subject_cid = Column(String, nullable=True)
    label_val = Column(String(64), nullable=False)
    action = Column(String(10), nullable=False, default="create")  # 'create' | 'negate'
    status = Column(String(10), nullable=False, default="pending", index=True)
    attempts = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=True)
    next_attempt_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    sent_at = Column(DateTime(timezone=True), nullable=True)
