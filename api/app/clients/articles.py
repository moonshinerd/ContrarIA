"""Texto completo de uma matéria a partir da URL da evidência.

Best-effort: sites com paywall ou que bloqueiam scraping devolvem None, e quem
chama usa o snippet da busca no lugar.
"""

import logging

import httpx

logger = logging.getLogger("contraria.clients.articles")

_USER_AGENT = "ContrarIA/1.0 (+https://github.com/moonshinerd/ContrarIA)"


async def fetch_article_text(url: str, *, max_chars: int) -> str | None:
    try:
        from bs4 import BeautifulSoup

        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            response = await client.get(url, headers={"User-Agent": _USER_AGENT})
            response.raise_for_status()
        soup = BeautifulSoup(response.text, "lxml")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
            tag.decompose()
        text = " ".join(soup.get_text(" ").split())
        return text[:max_chars] if text else None
    except Exception as exc:
        logger.info("Não foi possível buscar a página completa de %s: %s", url, type(exc).__name__)
        return None
