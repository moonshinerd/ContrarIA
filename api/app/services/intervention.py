import logging

from app.clients.bluesky_client import BlueskyClient
from app.core.config import get_settings
from app.domain.entities import Account, Post, Verdict, VerdictLabel
from app.models.llm.base import LLMPort
from app.repositories.interventions import InterventionRepository
from app.services.prompts_loader import load_prompt

logger = logging.getLogger("contraria.services.intervention")


class InterventionService:
    def __init__(
        self,
        repo: InterventionRepository,
        bsky_client: BlueskyClient,
        llm: LLMPort,
    ):
        self.repo = repo
        self.bsky_client = bsky_client
        self.llm = llm
        self.settings = get_settings()

    async def _should_intervene(self, post: Post, author: Account, verdict: Verdict) -> bool:
        # Só intervém se for falso ou enganoso com alta confiança
        if verdict.label not in (VerdictLabel.FALSE, VerdictLabel.MISLEADING):
            return False

        if verdict.confidence < 0.8:
            logger.info(
                "Confiança do veredito muito baixa para intervenção (%f)", verdict.confidence
            )
            return False

        # Anti-loop 1: Nunca citar posts do próprio bot
        bot_did = await self.bsky_client.login()
        if post.author_did == bot_did:
            return False

        # Anti-loop 2: Nunca citar posts de contas com self-label bot que citaram o ContrarIA
        # (Para simplificar: evitamos contas declaradas bot)
        if "bot" in author.self_labels + author.labels:
            logger.info("Alvo %s é self-labeled bot", author.handle)
            return False

        # Anti-loop 3: 1 quote por post
        if self.repo.has_intervened_on_post(post.uri, "quote_post"):
            logger.info("Já interveio no post %s", post.uri)
            return False

        # Anti-loop 4: 1 quote por autor a cada 24h
        if self.repo.count_interventions_by_author_in_last_24h(post.author_did, "quote_post") >= 1:
            logger.info("Autor %s já recebeu intervenção nas últimas 24h", post.author_did)
            return False

        # Trava diária
        daily_max = getattr(self.settings, "daily_max_interventions", 20)
        if self.repo.count_interventions_in_last_24h("quote_post") >= daily_max:
            logger.info("Limite diário de intervenções atingido (%d)", daily_max)
            return False

        # Postgate
        if await self.bsky_client.has_postgate_quote_disabled(post.uri):
            logger.info("Post %s tem postgate desabilitando quote", post.uri)
            return False

        return True

    async def execute_intervention(
        self, post: Post, author: Account, verdict: Verdict, bot_score: float
    ) -> str | None:
        if not await self._should_intervene(post, author, verdict):
            return None

        # Determinar tom
        target_tone = "bot" if bot_score > 0.8 else "human"

        # Fonte principal (obrigatório >= 1 url de fonte)
        if not verdict.evidences:
            logger.info("Sem evidências para citar a fonte")
            return None
        source_url = verdict.evidences[0].url

        prompt_template = load_prompt("quote_post")
        prompt = prompt_template.format(
            claim=verdict.claim, rationale=verdict.rationale, tone=target_tone
        )

        logger.info("Gerando texto de intervenção (LLM)...")
        generated_text = await self.llm.generate(prompt)

        # Guardrails pós-geração
        if len(generated_text) > 280:
            generated_text = generated_text[:277] + "..."

        is_dry_run = getattr(self.settings, "intervention_dry_run", True)

        if is_dry_run:
            logger.info(
                "[DRY RUN] Intervenção gerada (não publicada): %s | Fonte: %s",
                generated_text,
                source_url,
            )
            self.repo.record_intervention(post.uri, post.author_did, "quote_post")
            return "dry_run_uri"

        logger.info("Publicando quote post para %s...", post.uri)
        try:
            quote_uri = await self.bsky_client.quote_post(
                target_uri=post.uri, target_cid=post.cid, text=generated_text, source_url=source_url
            )
            self.repo.record_intervention(post.uri, post.author_did, "quote_post")
            return quote_uri
        except Exception as e:
            logger.error("Falha ao publicar quote post: %s", e)
            return None
