import litellm

from app.models.llm.model_limits import get_max_input_tokens


def test_limit_comes_from_litellm_catalog(monkeypatch):
    # O catálogo do litellm é baixado da rede e muda sem aviso; o teste fixa a resposta.
    monkeypatch.setattr(
        litellm, "get_model_info", lambda model: {"max_input_tokens": 400_000}, raising=True
    )
    assert get_max_input_tokens("openrouter/openai/gpt-5-mini", fallback=1) == 400_000


def test_unknown_model_uses_configured_fallback():
    assert get_max_input_tokens("unknown-provider/unknown-model", fallback=123_456) == 123_456
