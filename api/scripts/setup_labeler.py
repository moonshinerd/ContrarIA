import asyncio
import logging

from atproto import AsyncClient, models

from app.core.config import get_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("setup_labeler")


async def main() -> None:
    settings = get_settings()
    if not settings.bluesky_handle or not settings.bluesky_app_password:
        logger.error("Credenciais do bluesky não configuradas.")
        return

    client = AsyncClient(base_url=settings.bluesky_pds_url)
    await client.login(settings.bluesky_handle, settings.bluesky_app_password)

    # Declarar rótulos no app.bsky.labeler.service
    label_values = ["possivel-desinformacao", "provavel-bot", "evidencia-insuficiente"]

    label_definitions = [
        models.ComAtprotoLabelDefs.LabelValueDefinition(
            identifier="possivel-desinformacao",
            severity="inform",
            blurs="none",
            locales=[
                models.ComAtprotoLabelDefs.LabelValueDefinitionStrings(
                    lang="pt-BR",
                    name="Possível Desinformação",
                    description=(
                        "O modelo ou um checador identificou esta publicação como falsa ou "
                        "enganosa."
                    ),
                )
            ],
        ),
        models.ComAtprotoLabelDefs.LabelValueDefinition(
            identifier="provavel-bot",
            severity="inform",
            blurs="none",
            locales=[
                models.ComAtprotoLabelDefs.LabelValueDefinitionStrings(
                    lang="pt-BR",
                    name="Provável Bot",
                    description="Esta conta exibe comportamento automatizado ou inautêntico.",
                )
            ],
        ),
        models.ComAtprotoLabelDefs.LabelValueDefinition(
            identifier="evidencia-insuficiente",
            severity="inform",
            blurs="none",
            locales=[
                models.ComAtprotoLabelDefs.LabelValueDefinitionStrings(
                    lang="pt-BR",
                    name="Evidência Insuficiente",
                    description="Não há evidências suficientes para checar esta afirmação.",
                )
            ],
        ),
    ]

    policies = models.AppBskyLabelerDefs.LabelerPolicies(
        label_values=label_values,
        label_value_definitions=label_definitions,
    )

    record = models.AppBskyLabelerService.Record(
        policies=policies,
        created_at=client.get_current_time_iso(),
    )

    try:
        await client.com.atproto.repo.put_record(
            models.ComAtprotoRepoPutRecord.Data(
                repo=client.me.did,
                collection="app.bsky.labeler.service",
                rkey="self",
                record=record,
            )
        )
        logger.info("Rótulos declarados com sucesso no labeler service.")
    except Exception:
        logger.exception("Erro ao declarar rótulos")


if __name__ == "__main__":
    asyncio.run(main())
