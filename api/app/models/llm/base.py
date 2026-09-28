"""Porta abstrata de LLM.

Implementação concreta (LiteLLM: OpenRouter ou Ollama local) entra na issue do
cliente LLM. Serviços dependem só desta porta, então testes usam um fake.
"""

from abc import ABC, abstractmethod


class LLMPort(ABC):
    @abstractmethod
    async def complete(
        self,
        system: str,
        user: str,
        *,
        json_mode: bool = False,
        role: str | None = None,
        purpose: str = "general",
    ) -> str:
        """Retorna o texto (ou JSON serializado, se json_mode) gerado pelo modelo."""
