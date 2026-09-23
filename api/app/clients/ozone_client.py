import logging
from typing import Literal

from atproto import AsyncClient, models
from atproto_client.exceptions import RequestException

from app.core.config import get_settings
from app.domain.entities import Account, Post

logger = logging.getLogger("contraria.ozone")


class OzoneClient:
    """Cliente para interagir com o serviço de moderação Ozone."""

    def __init__(self, client: AsyncClient):
        self.client = client
        self.settings = get_settings()

    async def emit_label(
        self,
        target: Post | Account,
        label_val: str,
        action: Literal["create", "negate"] = "create",
    ) -> None:
        """
        Emite ou nega um rótulo usando tools.ozone.moderation.emitEvent.
        """
        if not self.settings.ozone_labeler_did:
            logger.warning("OZONE_LABELER_DID não configurado, pulando emissão de rótulo.")
            return

        if isinstance(target, Post):
            subject = models.ComAtprotoRepoStrongRef.Main(
                uri=target.uri,
                cid=target.cid,
            )
        else:
            subject = models.ComAtprotoAdminDefs.RepoRef(
                did=target.did,
            )

        event = models.ToolsOzoneModerationDefs.ModEventLabel(
            create_label_vals=[label_val] if action == "create" else [],
            negate_label_vals=[label_val] if action == "negate" else [],
        )

        try:
            # Emitimos o evento usando o proxy header pro atproto_labeler
            client_proxied = self.client.with_proxy(
                "atproto_labeler", self.settings.ozone_labeler_did
            )
            await client_proxied.tools.ozone.moderation.emit_event(
                data=models.ToolsOzoneModerationEmitEvent.Data(
                    event=event,
                    subject=subject,
                    created_by=self.client.me.did,
                )
            )
            logger.info(f"Rótulo {label_val} {action}d em {target}")
        except RequestException as e:
            logger.error(f"Erro ao emitir rótulo: {e}")
            raise
