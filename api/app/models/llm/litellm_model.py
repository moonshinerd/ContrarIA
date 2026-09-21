"""Cliente LLM unificado usando LiteLLM com suporte a OpenRouter e Ollama local.

Implementa LLMPort com suporte a modo JSON, retries com backoff, timeout,
configuração de modelos por papel e trava de orçamento diário (RNF05).
"""

import logging
import os
from datetime import date
from typing import Any

import litellm

from app.core.config import Settings, get_settings
from app.models.llm.base import LLMPort

logger = logging.getLogger(__name__)


class BudgetExceeded(Exception):
    """Lançada quando o gasto diário de LLM atinge ou ultrapassa DAILY_LLM_BUDGET_USD."""


class UsageTracker:
    """Rastreador de consumo e custos de chamadas a LLM."""

    def __init__(self) -> None:
        self._records: list[dict[str, Any]] = []

    def record(
        self,
        usage_date: date,
        model: str,
        purpose: str,
        tokens_in: int,
        tokens_out: int,
        cost_usd: float,
    ) -> None:
        """Registra o uso de tokens e custo de uma chamada."""
        record_data = {
            "date": usage_date,
            "model": model,
            "purpose": purpose,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "cost_usd": cost_usd,
        }
        self._records.append(record_data)

        # Tenta persistir no banco se a tabela/conexão estiver disponível
        try:
            from sqlalchemy import create_engine
            from sqlalchemy.orm import Session

            from app.db.orm.llm_usage import LLMUsage

            settings = get_settings()
            engine = create_engine(settings.database_url, pool_pre_ping=True)
            with Session(engine) as session:
                entry = LLMUsage(
                    date=usage_date,
                    model=model,
                    purpose=purpose,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    cost_usd=cost_usd,
                )
                session.add(entry)
                session.commit()
        except Exception:
            # Fallback transparente para ambientes sem banco (ex: testes rápidos, CI sem DB)
            pass

    def get_daily_cost(self, usage_date: date) -> float:
        """Calcula o custo total acumulado para a data fornecida."""
        # Se houver conexão com o banco, podemos consultar o total do dia
        try:
            from sqlalchemy import create_engine, func, select
            from sqlalchemy.orm import Session

            from app.db.orm.llm_usage import LLMUsage

            settings = get_settings()
            engine = create_engine(settings.database_url, pool_pre_ping=True)
            with Session(engine) as session:
                total_db = session.scalar(
                    select(func.coalesce(func.sum(LLMUsage.cost_usd), 0.0)).where(
                        LLMUsage.date == usage_date
                    )
                )
                if total_db is not None and total_db > 0.0:
                    return float(total_db)
        except Exception:
            pass

        # Fallback para o acumulador em memória
        return sum(r["cost_usd"] for r in self._records if r["date"] == usage_date)

    def reset(self) -> None:
        """Limpa os registros em memória (útil para testes unitários)."""
        self._records.clear()


default_usage_tracker = UsageTracker()


class LiteLLMModel(LLMPort):
    """Implementação de LLMPort via LiteLLM."""

    def __init__(
        self,
        settings: Settings | None = None,
        tracker: UsageTracker | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.tracker = tracker or default_usage_tracker

    def _resolve_model(self, role: str | None = None) -> str:
        """Seleciona o modelo adequado conforme o papel ou usa o padrão."""
        if role:
            normalized = role.strip().lower()
            if normalized in ("prosecutor", "promotor") and self.settings.llm_model_prosecutor:
                return self.settings.llm_model_prosecutor
            if normalized in ("defender", "defensor") and self.settings.llm_model_defender:
                return self.settings.llm_model_defender
            if normalized in ("judge", "juiz") and self.settings.llm_model_judge:
                return self.settings.llm_model_judge
        return self.settings.llm_model_name

    def _resolve_api_params(self, model: str) -> dict[str, Any]:
        """Configura credenciais e base_url de acordo com o provedor."""
        params: dict[str, Any] = {}

        if model.startswith("openrouter/"):
            api_key = (
                self.settings.openrouter_api_key
                or self.settings.llm_api_key
                or os.environ.get("OPENROUTER_API_KEY")
            )
            if api_key:
                params["api_key"] = api_key
            if self.settings.llm_api_base_url:
                params["api_base"] = self.settings.llm_api_base_url

        elif model.startswith("ollama/"):
            api_base = (
                self.settings.llm_api_base_url
                or os.environ.get("OLLAMA_API_BASE")
                or "http://host.docker.internal:11434"
            )
            params["api_base"] = api_base
        else:
            if self.settings.llm_api_key:
                params["api_key"] = self.settings.llm_api_key
            if self.settings.llm_api_base_url:
                params["api_base"] = self.settings.llm_api_base_url

        return params

    async def complete(
        self,
        system: str,
        user: str,
        *,
        json_mode: bool = False,
        role: str | None = None,
        purpose: str = "general",
    ) -> str:
        """Executa a conclusão do modelo via LiteLLM com verificação de orçamento."""
        today = date.today()
        current_spent = self.tracker.get_daily_cost(today)
        if current_spent >= self.settings.daily_llm_budget_usd:
            raise BudgetExceeded(
                f"Orçamento diário de LLM excedido: ${current_spent:.4f} consumidos de um limite "
                f"de ${self.settings.daily_llm_budget_usd:.2f}."
            )

        model = self._resolve_model(role)
        api_params = self._resolve_api_params(model)

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

        extra_kwargs: dict[str, Any] = {}
        if json_mode:
            extra_kwargs["response_format"] = {"type": "json_object"}

        response = await litellm.acompletion(
            model=model,
            messages=messages,
            timeout=self.settings.llm_timeout_seconds,
            num_retries=self.settings.llm_max_retries,
            **api_params,
            **extra_kwargs,
        )

        try:
            cost = litellm.completion_cost(completion_response=response)
        except Exception:
            cost = 0.0
        if cost is None:
            cost = 0.0

        tokens_in = 0
        tokens_out = 0
        if hasattr(response, "usage") and response.usage:
            tokens_in = getattr(response.usage, "prompt_tokens", 0) or 0
            tokens_out = getattr(response.usage, "completion_tokens", 0) or 0

        self.tracker.record(
            usage_date=today,
            model=model,
            purpose=purpose,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost,
        )

        content = response.choices[0].message.content or ""
        return content
