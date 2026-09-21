"""Configuração centralizada, lida de variáveis de ambiente / api/.env."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "ContrarIA"
    log_level: str = "INFO"
    database_url: str = "postgresql+psycopg://contraria:contraria@localhost:5432/contraria"

    bluesky_handle: str = ""
    bluesky_app_password: str = ""
    bluesky_pds_url: str = "https://bsky.social"
    # AppView pública: leituras sem login (getPosts, getProfile, getAuthorFeed)
    bluesky_appview_url: str = "https://public.api.bsky.app"
    # createSession tem limite de 300/dia: a sessão é persistida e reaproveitada
    bluesky_session_path: str = "data/bluesky.session"
    bluesky_max_retries: int = 3
    bluesky_max_backoff_seconds: float = 60.0

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
    # Cota real da Fact Check Tools API: 300 requisições/minuto (sem limite diário).
    # Ficamos com margem para não estourar quando api e worker consultam juntos.
    google_factcheck_rate_per_minute: int = 240
    tavily_api_key: str = ""

    tavily_enabled: bool = True
    duckduckgo_enabled: bool = True
    rss_checkers_enabled: bool = True
    web_search_days: int = Field(default=7, ge=1)
    web_cache_ttl_seconds: int = Field(default=3600, ge=1)
    web_cache_max_entries: int = Field(default=1000, ge=1)
    tavily_cooldown_seconds: int = Field(default=3600, ge=1)
    evidence_timeout_seconds: float = Field(default=20, gt=0)
    rss_poll_seconds: int = Field(default=3600, ge=60)
    rss_recency_weight: float = Field(default=0.1, ge=0, le=1)
    rss_recency_half_life_days: float = Field(default=30, gt=0)
    rss_min_similarity: float = Field(default=0.3, ge=-1, le=1)
    rss_enabled_sources: list[str] = [
        "lupa",
        "aos_fatos",
        "g1_fato_fake",
        "boatos",
        "comprova",
        "tse",
        "estadao_verifica",
        "uol_confere",
    ]
    rss_feed_urls: dict[str, str] = {}

    daily_llm_budget_usd: float = 1.0
    daily_max_interventions: int = 20

    worker_tick_seconds: int = 30


@lru_cache
def get_settings() -> Settings:
    return Settings()
