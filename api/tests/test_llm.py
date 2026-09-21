"""Testes unitários para o subsistema de LLM, fakes, carregador de prompts e controle de custos."""

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import Settings
from app.models.llm.litellm_model import BudgetExceeded, LiteLLMModel, UsageTracker
from app.services.prompts_loader import load_prompt
from tests.fakes import FakeLLM


@pytest.mark.anyio
async def test_fake_llm_scripted_responses():
    """Testa que FakeLLM devolve respostas roteirizadas em sequência e registra chamadas."""
    fake = FakeLLM(responses=["resposta 1", "resposta 2"], default_response="padrao")

    resp1 = await fake.complete(system="sys", user="usr1")
    resp2 = await fake.complete(system="sys", user="usr2", json_mode=True, role="judge")
    resp3 = await fake.complete(system="sys", user="usr3")

    assert resp1 == "resposta 1"
    assert resp2 == "resposta 2"
    assert resp3 == "padrao"

    assert fake.call_count == 3
    assert fake.last_call == {
        "system": "sys",
        "user": "usr3",
        "json_mode": False,
        "role": None,
        "purpose": "general",
    }
    assert fake.calls[1]["role"] == "judge"
    assert fake.calls[1]["json_mode"] is True


@pytest.mark.anyio
async def test_fake_llm_mapped_responses():
    """Testa que FakeLLM respeita mapeamento por papel ou palavra-chave."""
    fake = FakeLLM(
        responses={
            "promotor": '{"alegacao": "falsa"}',
            "defensor": '{"alegacao": "verdadeira"}',
        }
    )

    resp_promotor = await fake.complete(system="sys", user="post", role="promotor")
    resp_defensor = await fake.complete(system="sys", user="post", role="defensor")
    resp_outro = await fake.complete(system="sys", user="post", role="juiz")

    assert resp_promotor == '{"alegacao": "falsa"}'
    assert resp_defensor == '{"alegacao": "verdadeira"}'
    assert resp_outro == '{"status": "fake_ok"}'


def test_prompts_loader_success():
    """Testa carregamento de prompt existente."""
    content = load_prompt("smoke_test", version=1)
    assert "modelo de teste" in content


def test_prompts_loader_not_found():
    """Testa erro ao tentar carregar prompt inexistente."""
    with pytest.raises(FileNotFoundError):
        load_prompt("prompt_que_nao_existe", version=99)


def test_usage_tracker_daily_accumulation():
    """Testa acumulação em memória de custos de LLM."""
    tracker = UsageTracker()
    hoje = date.today()

    tracker.record(
        usage_date=hoje,
        model="openrouter/google/gemini-2.5-flash",
        purpose="triagem",
        tokens_in=100,
        tokens_out=50,
        cost_usd=0.0025,
    )
    tracker.record(
        usage_date=hoje,
        model="openrouter/google/gemini-2.5-flash",
        purpose="verificacao",
        tokens_in=200,
        tokens_out=100,
        cost_usd=0.0050,
    )

    assert pytest.approx(tracker.get_daily_cost(hoje), 0.0001) == 0.0075

    tracker.reset()
    assert tracker.get_daily_cost(hoje) == 0.0


def test_litellm_model_role_resolution():
    """Testa resolução de modelos por papel e fallback."""
    settings = Settings(
        llm_model_name="openrouter/google/gemini-2.5-flash",
        llm_model_prosecutor="openrouter/meta-llama/llama-3.3-70b-instruct",
        llm_model_judge="openrouter/anthropic/claude-3.5-sonnet",
    )
    model = LiteLLMModel(settings=settings)

    assert model._resolve_model("prosecutor") == "openrouter/meta-llama/llama-3.3-70b-instruct"
    assert model._resolve_model("promotor") == "openrouter/meta-llama/llama-3.3-70b-instruct"
    assert model._resolve_model("judge") == "openrouter/anthropic/claude-3.5-sonnet"
    assert model._resolve_model("juiz") == "openrouter/anthropic/claude-3.5-sonnet"
    # Defensor não configurado: faz fallback para modelo padrão
    assert model._resolve_model("defender") == "openrouter/google/gemini-2.5-flash"
    assert model._resolve_model(None) == "openrouter/google/gemini-2.5-flash"


def test_litellm_api_params_resolution():
    """Testa parâmetros de API para OpenRouter e Ollama."""
    settings = Settings(
        openrouter_api_key="sk-or-secret",
        llm_api_base_url="http://custom:11434",
    )
    model = LiteLLMModel(settings=settings)

    or_params = model._resolve_api_params("openrouter/google/gemini-2.5-flash")
    assert or_params["api_key"] == "sk-or-secret"

    ollama_params = model._resolve_api_params("ollama/qwen2.5:7b")
    assert ollama_params["api_base"] == "http://custom:11434"


@pytest.mark.anyio
async def test_litellm_budget_exceeded_blocking():
    """Testa bloqueio de chamada ao estourar o orçamento diário configurado."""
    tracker = UsageTracker()
    hoje = date.today()
    tracker.record(
        usage_date=hoje,
        model="openrouter/google/gemini-2.5-flash",
        purpose="teste",
        tokens_in=1000,
        tokens_out=1000,
        cost_usd=1.05,
    )

    settings = Settings(daily_llm_budget_usd=1.00)
    model = LiteLLMModel(settings=settings, tracker=tracker)

    with pytest.raises(BudgetExceeded) as exc_info:
        await model.complete(system="sys", user="user")

    assert "Orçamento diário de LLM excedido" in str(exc_info.value)


@pytest.mark.anyio
async def test_litellm_completion_execution_and_usage_recording():
    """Testa execução de complete() com mock do acompletion do litellm."""
    tracker = UsageTracker()
    settings = Settings(daily_llm_budget_usd=1.00)
    model = LiteLLMModel(settings=settings, tracker=tracker)

    fake_response = MagicMock()
    fake_choice = MagicMock()
    fake_choice.message.content = '{"veredicto": "falso"}'
    fake_response.choices = [fake_choice]
    fake_response.usage.prompt_tokens = 150
    fake_response.usage.completion_tokens = 40

    with (
        patch("litellm.acompletion", new_callable=AsyncMock) as mock_acompletion,
        patch("litellm.completion_cost", return_value=0.0012),
    ):
        mock_acompletion.return_value = fake_response

        res = await model.complete(
            system="sys",
            user="user",
            json_mode=True,
            role="promotor",
            purpose="debate",
        )

        assert res == '{"veredicto": "falso"}'
        mock_acompletion.assert_called_once()
        _, kwargs = mock_acompletion.call_args
        assert kwargs["response_format"] == {"type": "json_object"}
        assert kwargs["temperature"] == 0
        assert kwargs["timeout"] == 30.0

        # Verifica se o uso e custo foram computados
        assert pytest.approx(tracker.get_daily_cost(date.today()), 0.0001) == 0.0012
