import logging
from asyncio import Lock
from typing import Literal

from atproto import AsyncClient, models
from atproto_client.exceptions import RequestException

from app.core.config import Settings, get_settings
from app.domain.entities import Account, Post

logger = logging.getLogger("contraria.ozone")


class OzoneClient:
    """Cliente para interagir com o serviço de moderação Ozone."""

    def __init__(self, client: AsyncClient | None = None, settings: Settings | None = None):
        self.settings = settings or get_settings()
        # O Ozone deve autenticar como a conta de serviço do Labeler, nunca
        # como a conta que publica quotes pelo pipeline.
        self.client = client or AsyncClient(base_url=self.settings.bluesky_pds_url)
        self._logged_in = client is not None
        self._login_lock = Lock()

    async def _ensure_login(self) -> None:
        if self._logged_in:
            return
        if not self.settings.ozone_labeler_handle or not self.settings.ozone_labeler_app_password:
            raise RuntimeError(
                "OZONE_LABELER_HANDLE e OZONE_LABELER_APP_PASSWORD são obrigatórios "
                "para emitir rótulos"
            )
        async with self._login_lock:
            if not self._logged_in:
                await self.client.login(
                    login=self.settings.ozone_labeler_handle,
                    password=self.settings.ozone_labeler_app_password,
                    fetch_bsky_profile=False,
                )
                self._logged_in = True

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
            raise RuntimeError("OZONE_LABELER_DID não configurado; emissão de rótulo bloqueada")
        await self._ensure_login()

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
