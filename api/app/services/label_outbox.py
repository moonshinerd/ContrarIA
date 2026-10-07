"""Outbox de rótulos: registra cada emissão no banco e repete as que falharam.

O quote post já saiu quando o rótulo é pedido, então uma falha do Ozone (ex.: o
túnel do labeler fora do ar, 502) não pode simplesmente virar uma linha de log e
perder o rótulo. Cada pedido vira um `LabelEvent`; o worker chama `flush()` de
tempos em tempos e as falhas voltam com espera crescente até `label_retry_max_attempts`.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.clients.ozone_client import OzoneClient
from app.core.config import Settings
from app.db.orm.label_events import LabelEvent
from app.domain.entities import Account, Post

logger = logging.getLogger("contraria.services.label_outbox")

_MAX_BACKOFF = timedelta(hours=1)
_FLUSH_BATCH = 20


class LabelOutbox:
    def __init__(self, settings: Settings, db: Session, ozone: OzoneClient) -> None:
        self.settings = settings
        self.db = db
        self.ozone = ozone

    async def emit(
        self,
        target: Post | Account,
        label_val: str,
        action: Literal["create", "negate"] = "create",
    ) -> LabelEvent:
        """Registra o pedido e tenta enviar já; se falhar, fica pendente para repetir."""
        subject_kind, subject_uri, subject_cid = _describe(target)
        event = self.db.scalar(
            select(LabelEvent).where(
                LabelEvent.subject_uri == subject_uri,
                LabelEvent.label_val == label_val,
                LabelEvent.action == action,
                LabelEvent.status == "pending",
            )
        )
        if event is None:
            event = LabelEvent(
                subject_kind=subject_kind,
                subject_uri=subject_uri,
                subject_cid=subject_cid,
                label_val=label_val,
                action=action,
                status="pending",
                attempts=0,
            )
            self.db.add(event)
            self.db.commit()
        await self._attempt(event)
        return event

    async def flush(self, now: datetime | None = None) -> int:
        """Repete os pedidos pendentes já vencidos. Devolve quantos foram entregues."""
        current = now or datetime.now(UTC)
        events = self.db.scalars(
            select(LabelEvent)
            .where(and_(LabelEvent.status == "pending", LabelEvent.next_attempt_at <= current))
            .order_by(LabelEvent.id)
            .limit(_FLUSH_BATCH)
        ).all()
        delivered = 0
        for event in events:
            if await self._attempt(event, now=current):
                delivered += 1
        return delivered

    async def _attempt(self, event: LabelEvent, now: datetime | None = None) -> bool:
        current = now or datetime.now(UTC)
        try:
            await self.ozone.emit_label(
                _rebuild(event), label_val=event.label_val, action=event.action
            )
        except Exception as exc:
            self.db.rollback()
            event.attempts = (event.attempts or 0) + 1
            event.last_error = f"{type(exc).__name__}: {exc}"[:500]
            if event.attempts >= self.settings.label_retry_max_attempts:
                event.status = "failed"
                logger.error(
                    "Rótulo %s (%s) em %s desistiu após %d tentativas: %s",
                    event.label_val,
                    event.action,
                    event.subject_uri,
                    event.attempts,
                    event.last_error,
                )
            else:
                wait = min(
                    timedelta(seconds=self.settings.label_retry_interval_seconds)
                    * 2 ** (event.attempts - 1),
                    _MAX_BACKOFF,
                )
                event.next_attempt_at = current + wait
                logger.warning(
                    "Falha ao emitir rótulo %s em %s (tentativa %d), nova tentativa em %ds: %s",
                    event.label_val,
                    event.subject_uri,
                    event.attempts,
                    int(wait.total_seconds()),
                    event.last_error,
                )
            self.db.add(event)
            self.db.commit()
            return False
        event.attempts = (event.attempts or 0) + 1
        event.status = "sent"
        event.sent_at = current
        event.last_error = None
        self.db.add(event)
        self.db.commit()
        return True


def _describe(target: Post | Account) -> tuple[str, str, str | None]:
    if isinstance(target, Post):
        return "post", target.uri, target.cid
    return "account", target.did, None


def _rebuild(event: LabelEvent) -> Post | Account:
    if event.subject_kind == "post":
        return Post(
            uri=event.subject_uri,
            cid=event.subject_cid or "",
            author_did="",
            text="",
            created_at=datetime.now(UTC),
        )
    return Account(did=event.subject_uri, handle="")
