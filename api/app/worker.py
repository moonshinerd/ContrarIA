"""Worker de longa duração: roda o pipeline do ContrarIA em loop.

Esqueleto -- cada etapa entra pela issue correspondente (coleta, triagem,
bot score, verificação, intervenção). Rode com `python -m app.worker`.
"""

import asyncio
import logging

from app.core.config import get_settings
from app.core.logging import configure_logging

logger = logging.getLogger("contraria.worker")


async def main() -> None:
    settings = get_settings()
    configure_logging(settings)
    logger.info("worker started", extra={"tick_seconds": settings.worker_tick_seconds})
    while True:
        logger.info("worker tick")
        await asyncio.sleep(settings.worker_tick_seconds)


if __name__ == "__main__":
    asyncio.run(main())
