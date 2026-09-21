"""Registro das fontes da #21; preservar também o registro da #20 ao integrar o PR #37."""

from app.clients.evidence.base import EvidenceSource
from app.clients.evidence.rss_checkers import RSSCheckersSource
from app.clients.evidence.web_search import (
    DuckDuckGoClient,
    EvidenceSearchUnavailable,
    TavilyClient,
    WebSearchSource,
)
from app.core.config import get_settings

EVIDENCE_SOURCES: dict[str, type[EvidenceSource]] = {
    "tavily": TavilyClient,
    "duckduckgo": DuckDuckGoClient,
    "web_search": WebSearchSource,
    "rss_checkers": RSSCheckersSource,
}


def get_evidence_source(name: str, **kwargs) -> EvidenceSource:
    if name not in EVIDENCE_SOURCES:
        raise ValueError(f"Fonte desconhecida: {name}. Opções: {list(EVIDENCE_SOURCES)}")
    kwargs.setdefault("settings", get_settings())
    return EVIDENCE_SOURCES[name](**kwargs)


__all__ = [
    "EVIDENCE_SOURCES",
    "DuckDuckGoClient",
    "EvidenceSearchUnavailable",
    "EvidenceSource",
    "RSSCheckersSource",
    "TavilyClient",
    "WebSearchSource",
    "get_evidence_source",
]
