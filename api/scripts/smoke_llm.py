"""Script de smoke test para validação do cliente LiteLLM.

Executa com OpenRouter ou Ollama trocando apenas as variáveis no `.env`.
Uso:
    uv run python scripts/smoke_llm.py
    uv run python scripts/smoke_llm.py --test-budget
"""

import asyncio
import sys
from datetime import date
from pathlib import Path

# Adiciona o diretório da API ao sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import get_settings
from app.models.llm.litellm_model import BudgetExceeded, LiteLLMModel, default_usage_tracker
from app.services.prompts_loader import load_prompt


async def main() -> None:
    settings = get_settings()
    print("=== ContrarIA: Smoke Test de LLM ===")
    print(f"Modelo configurado: {settings.llm_model_name}")
    print(f"Orçamento diário:   ${settings.daily_llm_budget_usd:.2f}")

    hoje = date.today()
    gasto_atual = default_usage_tracker.get_daily_cost(hoje)
    print(f"Gasto hoje ({hoje}): ${gasto_atual:.4f}")

    model = LiteLLMModel(settings=settings)

    if "--test-budget" in sys.argv:
        print("\n[Simulação de Trava de Custo] Injetando consumo para ultrapassar limite...")
        default_usage_tracker.record(
            usage_date=hoje,
            model=settings.llm_model_name,
            purpose="teste_trava",
            tokens_in=5000,
            tokens_out=5000,
            cost_usd=settings.daily_llm_budget_usd + 0.10,
        )
        try:
            await model.complete(system="sys", user="teste")
            print("❌ ERRO: A chamada deveria ter sido bloqueada por BudgetExceeded!")
            sys.exit(1)
        except BudgetExceeded as e:
            print(f"✅ SUCESSO: Chamada bloqueada corretamente! ({e})")
            return

    system_prompt = load_prompt("smoke_test", version=1)
    user_prompt = "Responda apenas: 'ContrarIA online' se você estiver funcionando."

    print("\nEnviando requisição de teste...")
    try:
        resposta = await model.complete(system=system_prompt, user=user_prompt)
        print("\n--- Resposta do Modelo ---")
        print(resposta)
        print("---------------------------")
        novo_gasto = default_usage_tracker.get_daily_cost(hoje)
        print(f"Novo gasto acumulado hoje: ${novo_gasto:.4f}")
        print("✅ Smoke test concluído com sucesso!")
    except BudgetExceeded as e:
        print(f"⚠️ Orçamento estourado: {e}")
    except Exception as e:
        print(f"❌ Falha na execução da chamada: {e}")
        print("Dica: verifique se OPENROUTER_API_KEY ou Ollama estão configurados no seu .env.")


if __name__ == "__main__":
    asyncio.run(main())
