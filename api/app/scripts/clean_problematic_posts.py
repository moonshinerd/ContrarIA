"""Script utilitário para auditar e apagar posts problemáticos do bot no Bluesky.

Uso:
    python -m app.scripts.clean_problematic_posts [--uris URI [URI ...]] [--dry-run]
"""

import argparse
import asyncio
import logging

from app.clients.bluesky_client import BlueskyClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Posts problemáticos identificados na auditoria de 15/10/2026:
DEFAULT_PROBLEMATIC_URIS = [
    # 1. Flávio Bolsonaro / Aposentadorias (atribuição forjada de entrevista a debate eleitoral)
    "at://did:plc:p3rfvq6b4rp7jnc3oqpzhrlr/app.bsky.feed.post/3mxx3ypnf7n2l",
    # 2. Caso Copacabana (atribuição forjada de fotos de IA a multidão real)
    "at://did:plc:p3rfvq6b4rp7jnc3oqpzhrlr/app.bsky.feed.post/3mxvs45c23325",
    # 3. Fragmento órfão de thread Copacabana
    "at://did:plc:p3rfvq6b4rp7jnc3oqpzhrlr/app.bsky.feed.post/3mxvpk34xcc24",
    # 4. Outro caso Copacabana
    "at://did:plc:p3rfvq6b4rp7jnc3oqpzhrlr/app.bsky.feed.post/3mxv4n5hois2i",
    # 5. Caso Tigrinho / Erika Hilton (cópia verbatim do post original)
    "at://did:plc:p3rfvq6b4rp7jnc3oqpzhrlr/app.bsky.feed.post/3mxuyebql5r24",
    # 6. Fragmento de thread Tigrinho / Erika Hilton
    "at://did:plc:p3rfvq6b4rp7jnc3oqpzhrlr/app.bsky.feed.post/3mxuyebxk7r2u",
    # 7. Caso Tigrinho / Desabafo Temer e IPVA (desabafo coloquial)
    "at://did:plc:p3rfvq6b4rp7jnc3oqpzhrlr/app.bsky.feed.post/3mxuwmrca5d24",
]


async def clean_posts(uris: list[str] | None = None, dry_run: bool = False) -> dict[str, list[str]]:
    target_uris = uris if uris is not None else DEFAULT_PROBLEMATIC_URIS
    deleted: list[str] = []
    failed: list[str] = []
    client = BlueskyClient()
    try:
        did = await client.login()
        logger.info("Autenticado no Bluesky com DID: %s", did)

        for uri in target_uris:
            if not uri.startswith("at://"):
                logger.warning("URI inválido ignorado: %s", uri)
                continue

            if dry_run:
                logger.info("[DRY RUN] Post seria apagado: %s", uri)
                deleted.append(uri)
            else:
                logger.info("Apagando post: %s...", uri)
                success = await client.delete_post(uri)
                if success:
                    deleted.append(uri)
                    logger.info("Sucesso ao apagar: %s", uri)
                else:
                    failed.append(uri)
                    logger.error("Falha ao apagar: %s", uri)
    finally:
        await client.close()

    return {"deleted": deleted, "failed": failed}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--uris",
        nargs="*",
        default=DEFAULT_PROBLEMATIC_URIS,
        help="Lista de URIs AT Protocol a serem apagados.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Apenas simula a deleção sem remover no Bluesky.",
    )
    args = parser.parse_args()

    asyncio.run(clean_posts(args.uris, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
