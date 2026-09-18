"""Módulo de fontes de evidência externas."""

from typing import Dict, Type
from app.clients.evidence.base import EvidenceSource
from app.clients.evidence.wikipedia import WikipediaClient
from app.clients.evidence.google_factcheck import GoogleFactCheckClient

# Registro de fontes disponíveis por identificador
EVIDENCE_SOURCES: Dict[str, Type[EvidenceSource]] = {
    WikipediaClient.name: WikipediaClient,
    GoogleFactCheckClient.name: GoogleFactCheckClient,
}


def get_evidence_source(name: str, **kwargs) -> EvidenceSource:
    """Instancia uma fonte de evidência registrada a partir do seu nome."""
    source_cls = EVIDENCE_SOURCES.get(name)
    if not source_cls:
        raise ValueError(f"Fonte de evidência desconhecida: '{name}'. Opções: {list(EVIDENCE_SOURCES.keys())}")
    return source_cls(**kwargs)


__all__ = [
    "EvidenceSource",
    "WikipediaClient",
    "GoogleFactCheckClient",
    "EVIDENCE_SOURCES",
    "get_evidence_source",
]