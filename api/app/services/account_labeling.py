"""Rótulo `provavel-bot` em contas, emitido pelo labeler Ozone.

Roda para toda conta analisada pelo pipeline, não só para as que recebem quote post.
O estado (`account_assessments.bot_label_applied`) evita emitir de novo a cada análise
e permite negar o rótulo quando o score cai. A histerese impede que uma conta perto do
limiar fique ganhando e perdendo o rótulo.
"""

import logging

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.clients.ozone_client import OzoneClient
from app.core.config import Settings
from app.db.orm.bots import AccountAssessment
from app.domain.entities import Account

logger = logging.getLogger("contraria.services.account_labeling")

BOT_LABEL = "provavel-bot"


class AccountLabelService:
    def __init__(self, settings: Settings, db: Session, ozone: OzoneClient) -> None:
        self.settings = settings
        self.db = db
        self.ozone = ozone

    async def sync(self, account: Account, score: float) -> str | None:
        """Aplica ou nega o rótulo conforme o score. Devolve "create", "negate" ou None.

        Falhas do Ozone viram log: o estado só muda depois de a emissão dar certo, então
        a próxima análise tenta de novo e a análise do post nunca é interrompida.
        """
        if not self.settings.pipeline_labeler_enabled:
            return None
        applied = self.db.scalar(
            select(AccountAssessment.bot_label_applied).where(AccountAssessment.did == account.did)
        )
        if applied is None:  # sem avaliação gravada: nada a registrar
            return None

        threshold = self.settings.account_label_threshold
        if (
            not applied
            and score >= threshold
            and account.posts_count >= self.settings.account_label_min_posts
        ):
            action = "create"
        elif applied and score < threshold - self.settings.account_label_hysteresis:
            action = "negate"
        else:
            return None

        try:
            await self.ozone.emit_label(account, label_val=BOT_LABEL, action=action)
        except Exception as exc:
            logger.error("Falha ao %s o rótulo %s em %s: %s", action, BOT_LABEL, account.did, exc)
            return None

        self.db.execute(
            update(AccountAssessment)
            .where(AccountAssessment.did == account.did)
            .values(bot_label_applied=action == "create")
        )
        self.db.commit()
        logger.info("Rótulo %s: %s em %s (score %.2f)", BOT_LABEL, action, account.did, score)
        return action
