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
    thread_context_max_posts: int = Field(default=4, ge=0, le=20)
    thread_context_max_chars: int = Field(default=3000, ge=0, le=12000)

    llm_model_name: str = "openrouter/google/gemini-2.5-flash"
    llm_api_key: str = ""
    openrouter_api_key: str = ""
    llm_api_base_url: str = ""

    llm_model_prosecutor: str = ""
    llm_model_defender: str = ""
    llm_model_judge: str = ""
    llm_timeout_seconds: float = 30.0
    llm_max_retries: int = 3
    # GPT-5 mini oferece 400k tokens de contexto. A revisão de fontes reserva
    # espaço para instruções/saída e organiza o restante em lotes conservadores.
    llm_context_window_tokens: int = Field(default=400_000, ge=8_000)
    llm_source_review_input_budget_tokens: int = Field(default=320_000, ge=4_000)
    llm_source_review_max_chars: int = Field(default=2_500_000, ge=10_000)
    llm_source_review_max_batches: int = Field(default=3, ge=1, le=20)
    debate_rounds: int = 2
    debate_p_ik_threshold: float = 0.60
    crc_alpha: float = Field(default=0.05, gt=0, lt=1)
    crc_model_name: str = ""

    # Backend de verificação: "llm" (CoVe + Self-RAG + debate multiagente na
    # nuvem, o caminho calibrado e validado) ou "jev" (classificação local via
    # logprobs de um modelo pequeno, sem geração de JSON -- mais rápido e
    # barato, mas o veredito final ainda não passou pela mesma validação
    # extensa do backend "llm"). O LLM continua sendo usado nos dois casos
    # para escrever o texto da intervenção socrática.
    verification_backend: str = "llm"
    jev_model_repo: str = "MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7"
    jev_model_file: str = ""
    jev_n_ctx: int = 512
    jev_n_threads: int = 0  # 0 = deixa o framework escolher
    # URL do serviço `jev` (app/jev_server.py): uma cópia única do modelo
    # compartilhada por api/worker/scripts. Vazio = carrega o modelo no
    # próprio processo (só para script avulso/teste manual -- nunca com
    # vários processos ao mesmo tempo, ver docstring de get_jev_classifier).
    jev_server_url: str = ""
    # Só para testes ao vivo antes de existir calibração do Jev: sem ela, o
    # veredito passa sem o gate CRC em vez de virar abstenção. Nunca em produção.
    jev_allow_uncalibrated: bool = False

    google_factcheck_api_key: str = ""
    # Cota real da Fact Check Tools API: 300 requisições/minuto (sem limite diário).
    # Ficamos com margem para não estourar quando api e worker consultam juntos.
    google_factcheck_rate_per_minute: int = 240

    searxng_enabled: bool = True
    searxng_base_url: str = "http://searxng:8080"
    searxng_categories: str = "news,general"
    searxng_language: str = "pt-BR"
    duckduckgo_enabled: bool = True
    rss_checkers_enabled: bool = True
    web_search_days: int = Field(default=7, ge=1)
    web_cache_ttl_seconds: int = Field(default=3600, ge=1)
    web_cache_max_entries: int = Field(default=1000, ge=1)
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

    # Self-RAG (#23): #20 por padrão; fontes da #21 entram pela lista quando desejado.
    self_rag_enabled_sources: list[str] = ["google_factcheck", "wikipedia"]
    self_rag_max_questions: int = Field(default=10, ge=1, le=100)
    self_rag_max_evidence_per_source: int = Field(default=3, ge=1, le=20)
    self_rag_max_llm_calls: int = Field(default=30, ge=1, le=300)

    daily_llm_budget_usd: float = 1.0
    daily_max_interventions: int = 30
    daily_write_points_budget: int = 150
    intervention_write_points: int = 3
    intervention_dry_run: bool = True
    # Worker: a cada N minutos publica só o candidato mais confiante da rodada
    # (diretriz de bots do Bluesky contra volume de interações não solicitadas).
    intervention_round_minutes: int = 15
    # Pausa diária (horário de Brasília, UTC-3): sem ela, a conta nunca fica 4h
    # parada, sinal usado para marcar bots de resposta automática.
    intervention_quiet_start_hour: int = 0
    intervention_quiet_end_hour: int = 7
    worker_tick_seconds: int = 30
    triage_threshold_relevance: float = 1.0
    triage_threshold_bot: float = 0.8
    triage_threshold_falsehood: float = 0.8
    worker_pipeline_batch_size: int = 5
    pipeline_bot_scoring_enabled: bool = True
    pipeline_verification_enabled: bool = True
    pipeline_intervention_enabled: bool = True
    # A label is an externally visible moderation action. Keep it opt-in even
    # when quote generation is configured as dry-run.
    pipeline_labeler_enabled: bool = False
    pipeline_bot_ignore_threshold: float = Field(default=0.9, ge=0, le=1)
    pipeline_min_followers_for_intervention: int = Field(default=1000, ge=0)
    # Rótulo `provavel-bot` em contas: emitido quando o bot score passa do limiar e
    # negado quando cai abaixo de (limiar - histerese), para não oscilar. Só age com
    # `pipeline_labeler_enabled`.
    account_label_threshold: float = Field(default=0.9, ge=0, le=1)
    account_label_hysteresis: float = Field(default=0.1, ge=0, le=1)
    account_label_min_posts: int = Field(default=20, ge=0)
    ozone_labeler_handle: str = ""
    ozone_labeler_app_password: str = ""
    ozone_labeler_did: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
