"""Texto de uma matéria a partir da URL da evidência.

Best-effort: sites com paywall ou que bloqueiam scraping devolvem None, e quem
chama usa o snippet da busca no lugar.
"""

import logging

import httpx

logger = logging.getLogger("contraria.clients.articles")

_USER_AGENT = "ContrarIA/1.0 (+https://github.com/moonshinerd/ContrarIA)"


async def fetch_article_text(url: str, *, max_chars: int | None = None) -> str | None:
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            response = await client.get(url, headers={"User-Agent": _USER_AGENT})
            response.raise_for_status()

        # 1. Tenta extração de alta fidelidade com trafilatura
        try:
            import trafilatura

            extracted = trafilatura.extract(response.text, url=url, include_comments=False)
            if extracted and len(extracted.strip()) >= 50:
                text = " ".join(extracted.split())
                return text[:max_chars] if max_chars is not None else text
        except Exception:
            pass

        # 2. Fallback para BeautifulSoup
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(response.text, "lxml")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
            tag.decompose()
        text = " ".join(soup.get_text(" ").split())
        if not text:
            return None
        return text[:max_chars] if max_chars is not None else text
    except Exception as exc:
        logger.info("Não foi possível buscar a página completa de %s: %s", url, type(exc).__name__)
        return None
