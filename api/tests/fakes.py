"""Fakes para testes unitários e de integração das tarefas do ContrarIA."""

from typing import Any

from app.models.llm.base import LLMPort


class FakeLLM(LLMPort):
    """Implementação fake de LLMPort com respostas roteirizadas para testes."""

    def __init__(
        self,
        responses: list[str] | dict[str, str] | None = None,
        default_response: str = '{"status": "fake_ok"}',
    ) -> None:
        self._responses_list: list[str] = list(responses) if isinstance(responses, list) else []
        self._responses_map: dict[str, str] = dict(responses) if isinstance(responses, dict) else {}
        self.default_response = default_response
        self.calls: list[dict[str, Any]] = []

    @property
    def call_count(self) -> int:
        """Número total de chamadas feitas ao FakeLLM."""
        return len(self.calls)

    @property
    def last_call(self) -> dict[str, Any] | None:
        """Última chamada registrada, ou None se nenhuma foi feita."""
        return self.calls[-1] if self.calls else None

    async def complete(
        self,
        system: str,
        user: str,
        *,
        json_mode: bool = False,
        role: str | None = None,
        purpose: str = "general",
    ) -> str:
        """Registra a chamada e devolve a resposta roteirizada correspondente."""
        call_info = {
            "system": system,
            "user": user,
            "json_mode": json_mode,
            "role": role,
            "purpose": purpose,
        }
        self.calls.append(call_info)

        if self._responses_list:
            return self._responses_list.pop(0)

        if role and role in self._responses_map:
            return self._responses_map[role]

        if purpose and purpose in self._responses_map:
            return self._responses_map[purpose]

        for key, value in self._responses_map.items():
            if key in user:
                return value

        return self.default_response

    def reset(self) -> None:
        """Limpa as chamadas registradas."""
        self.calls.clear()
