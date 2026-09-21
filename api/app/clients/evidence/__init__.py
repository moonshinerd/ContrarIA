"""Módulo de fontes de evidência externas."""

import inspect

from app.clients.evidence.base import EvidenceSource
from app.clients.evidence.google_factcheck import GoogleFactCheckClient
from app.clients.evidence.rss_checkers import RSSCheckersSource
from app.clients.evidence.web_search import (
    DuckDuckGoClient,
    EvidenceSearchUnavailable,
    TavilyClient,
    WebSearchSource,
)
from app.clients.evidence.wikipedia import WikipediaClient
from app.core.config import get_settings

# Registro de fontes disponíveis por identificador
EVIDENCE_SOURCES: dict[str, type[EvidenceSource]] = {
    WikipediaClient.name: WikipediaClient,
    GoogleFactCheckClient.name: GoogleFactCheckClient,
    TavilyClient.name: TavilyClient,
    DuckDuckGoClient.name: DuckDuckGoClient,
    WebSearchSource.name: WebSearchSource,
    RSSCheckersSource.name: RSSCheckersSource,
}


def get_evidence_source(name: str, **kwargs) -> EvidenceSource:
    """Retorna uma instância da fonte de evidência pelo nome registrado.

    As fontes das issues #21 (busca web e RSS) recebem `Settings`; as demais
    (Wikipedia, Google Fact Check) leem a configuração por conta própria.
    """
    source_cls = EVIDENCE_SOURCES.get(name)
    if not source_cls:
        raise ValueError(
            f"Fonte de evidência desconhecida: '{name}'. Opções: {list(EVIDENCE_SOURCES.keys())}"
        )
    if "settings" in inspect.signature(source_cls).parameters:
        kwargs.setdefault("settings", get_settings())
    return source_cls(**kwargs)


__all__ = [
    "EvidenceSource",
    "EvidenceSearchUnavailable",
    "WikipediaClient",
    "GoogleFactCheckClient",
    "TavilyClient",
    "DuckDuckGoClient",
    "WebSearchSource",
    "RSSCheckersSource",
    "EVIDENCE_SOURCES",
    "get_evidence_source",
]
