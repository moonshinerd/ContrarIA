"""Configuração centralizada, lida de variáveis de ambiente / api/.env."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "ContrarIA"
    log_level: str = "INFO"
    database_url: str = "postgresql+psycopg://contraria:contraria@localhost:5432/contraria"

    bluesky_handle: str = ""
    bluesky_app_password: str = ""

    llm_model_name: str = "openrouter/google/gemini-2.5-flash"
    llm_api_key: str = ""
    openrouter_api_key: str = ""
    llm_api_base_url: str = ""

    llm_model_prosecutor: str = ""
    llm_model_defender: str = ""
    llm_model_judge: str = ""
    llm_timeout_seconds: float = 30.0
    llm_max_retries: int = 3

    google_factcheck_api_key: str = ""
    tavily_api_key: str = ""

    daily_llm_budget_usd: float = 1.0
    daily_max_interventions: int = 20

    worker_tick_seconds: int = 30


@lru_cache
def get_settings() -> Settings:
    return Settings()
