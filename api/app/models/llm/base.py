"""Porta abstrata de LLM.

Implementação concreta (LiteLLM: OpenRouter ou Ollama local) entra na issue do
cliente LLM. Serviços dependem só desta porta, então testes usam um fake.
"""

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import Any

ToolHandler = Callable[[str, dict[str, Any]], Awaitable[str]]


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

    async def complete_with_tools(
        self,
        system: str,
        user: str,
        *,
        tools: list[dict[str, Any]],
        call_tool: ToolHandler,
        max_tool_calls: int,
        purpose: str = "general",
    ) -> str:
        """Laço de tool calling: o modelo chama `tools` (schema OpenAI) via `call_tool`
        até `max_tool_calls` vezes e então responde em texto."""
        raise NotImplementedError
