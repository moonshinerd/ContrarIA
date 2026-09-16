"""Porta comum para fontes de evidência (RF11).

Cada fonte (Google Fact Check, Wikipedia, Tavily, DuckDuckGo, RSS/TSE) é uma
implementação desta classe -- permite ligar/desligar fontes no benchmark.
"""

from abc import ABC, abstractmethod

from app.domain.entities import Evidence


class EvidenceSource(ABC):
    name: str

    @abstractmethod
    async def search(self, query: str, *, limit: int = 5) -> list[Evidence]:
        """Busca evidências para uma alegação ou pergunta de verificação."""
