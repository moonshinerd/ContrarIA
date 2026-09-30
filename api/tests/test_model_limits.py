from app.models.llm.model_limits import get_max_input_tokens


def test_openrouter_gpt_5_mini_limit_comes_from_litellm_catalog():
    assert get_max_input_tokens("openrouter/openai/gpt-5-mini", fallback=1) == 400_000


def test_unknown_model_uses_configured_fallback():
    assert get_max_input_tokens("unknown-provider/unknown-model", fallback=123_456) == 123_456
