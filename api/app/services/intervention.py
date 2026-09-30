import asyncio
import logging
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any

from app.clients.articles import fetch_article_text
from app.clients.bluesky_client import BlueskyClient
from app.core.config import get_settings
from app.domain.entities import Account, Evidence, Post, Verdict, VerdictLabel
from app.models.llm.base import LLMPort
from app.models.llm.model_limits import get_max_input_tokens
from app.repositories.interventions import InterventionRepository
from app.services.prompts_loader import load_prompt

logger = logging.getLogger("contraria.services.intervention")

_AGGRESSIVE_TERMS = ("idiota", "burro", "imbecil", "estúpido", "estupido", "lixo")

_BLUESKY_LIMIT = 300
_THREAD_MARK = " 🧵"
_SOURCE_LABEL = " [Fonte]"

_BRASILIA = timezone(timedelta(hours=-3))

# A revisão lê as cinco fontes mais relevantes por inteiro. Quando o conjunto
# excede a janela de entrada, o texto é dividido em lotes sem descartar trechos.
_MAX_SOURCES_LISTED = 5
_MAX_ARTICLE_READS = 0
_CHARS_PER_TOKEN_ESTIMATE = 3
_SOURCE_REVIEW_RESERVED_TOKENS = 16_000
_TYPE_LINE = re.compile(r"\s*TIPO:\s*(\w+)[^\n]*\n?", re.IGNORECASE)
_VERDICT_LINE = re.compile(r"\s*VEREDITO:\s*(\w+)[^\n]*\n?", re.IGNORECASE)
_SOURCE_LINE = re.compile(r"\s*FONTE:\s*(\d+)[^\n]*\n?", re.IGNORECASE)
_ACTIONABLE_VERDICTS = {"DESMENTE", "DISTORCE"}


async def _no_tool_call(name: str, arguments: dict[str, Any]) -> str:
    """Defesa para a interface de tool calling; a redação final não usa ferramentas."""
    return "Não há ferramentas disponíveis nesta etapa; responda usando as revisões."


def _grapheme_len(text: str) -> int:
    """Conta aproximação de grafemas sem depender de biblioteca externa."""
    return sum(not unicodedata.combining(char) for char in text)


def _truncate_graphemes(text: str, limit: int) -> str:
    if _grapheme_len(text) <= limit:
        return text
    result: list[str] = []
    count = 0
    for char in text:
        if not unicodedata.combining(char):
            count += 1
        if count > limit - 1:
            break
        result.append(char)
    return "".join(result).rstrip() + "…"


def _format_sources(sources: list[Evidence]) -> str:
    return "\n".join(
        f"{index}. {item.title} ({item.url})\n   {item.snippet[:300]}"
        for index, item in enumerate(sources, start=1)
    )


def _split_text(text: str, max_chars: int) -> list[str]:
    """Divide texto preservando todos os caracteres e preferindo fronteira de palavra."""
    if len(text) <= max_chars:
        return [text]
    chunks: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= max_chars:
            chunks.append(remaining)
            break
        cut = remaining.rfind(" ", 0, max_chars + 1)
        if cut <= 0:
            cut = max_chars
        chunks.append(remaining[:cut])
        remaining = remaining[cut:]
    return chunks


def _build_source_batches(
    sources: list[Evidence], articles: list[str], input_budget_tokens: int
) -> list[str]:
    """Agrupa fontes inteiras em lotes que cabem na margem de contexto configurada."""
    max_chars = input_budget_tokens * _CHARS_PER_TOKEN_ESTIMATE
    batches: list[str] = []
    current = ""
    for number, (source, article) in enumerate(zip(sources, articles, strict=True), start=1):
        header = f"FONTE {number}: {source.title}\nURL: {source.url}\nTEXTO:\n"
        for part in _split_text(article, max_chars - len(header)):
            block = f"{header}{part}\n"
            if current and len(current) + len(block) > max_chars:
                batches.append(current)
                current = ""
            current += block
    if current:
        batches.append(current)
    return batches


def _parse_agent_output(text: str, sources: list[Evidence]) -> tuple[str, str | None]:
    """Lê `TIPO:`, `VEREDITO:` e `FONTE: n` e devolve (texto, url da fonte).

    url None = não publicar: o post é opinião/previsão (TIPO: OPINIAO), o
    agente concluiu CONFIRMA, ou não seguiu o formato (na dúvida, não responde).
    """
    claim_type = _TYPE_LINE.match(text)
    if not claim_type or claim_type.group(1).upper() != "FATO":
        return "", None
    text = text[claim_type.end() :]
    verdict = _VERDICT_LINE.match(text)
    if not verdict or verdict.group(1).upper() not in _ACTIONABLE_VERDICTS:
        return "", None
    rest = text[verdict.end() :]
    source = _SOURCE_LINE.match(rest)
    if not source:
        return rest, sources[0].url
    number = int(source.group(1))
    if number == 0:
        return "", None
    url = sources[number - 1].url if 1 <= number <= len(sources) else sources[0].url
    return rest[source.end() :], url


def _split_for_thread(text: str, limit: int = _BLUESKY_LIMIT) -> list[str]:
    """Quebra `text` em pedaços que cabem no limite do Bluesky.

    Reserva espaço (o maior dos dois) tanto para o emoji de thread (🧵, nos
    pedaços que não são o último) quanto para o link [Fonte] (no último),
    já que não sabemos até o fim da divisão qual pedaço será o último.
    """
    normalized = " ".join(text.split())
    reserve = max(_grapheme_len(_THREAD_MARK), _grapheme_len(_SOURCE_LABEL))
    budget = limit - reserve
    words = normalized.split(" ")
    chunks: list[str] = []
    current = ""
    for word in words:
        if _grapheme_len(word) > budget:
            word = _truncate_graphemes(word, budget)
        candidate = f"{current} {word}".strip()
        if _grapheme_len(candidate) > budget:
            if current:
                chunks.append(current)
            current = word
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks or [_truncate_graphemes(normalized, budget)]


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

        consumed_points = (
            self.repo.count_interventions_in_last_24h("quote_post")
            * self.settings.intervention_write_points
        )
        if (
            consumed_points + self.settings.intervention_write_points
            > self.settings.daily_write_points_budget
        ):
            logger.info("Orçamento diário de pontos de escrita atingido")
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
        candidate_sources = verdict.evidences[:_MAX_SOURCES_LISTED]

        async def fetch_source(source: Evidence) -> str | None:
            logger.info("Lendo obrigatoriamente a fonte: %s", source.url)
            return await fetch_article_text(source.url)

        article_results = await asyncio.gather(
            *(fetch_source(source) for source in candidate_sources)
        )
        readable_pairs = [
            (source, text)
            for source, text in zip(candidate_sources, article_results, strict=True)
            if text
        ]
        if not readable_pairs:
            logger.info("Nenhuma fonte pôde ser lida integralmente; não intervém")
            return None
        sources = [source for source, _ in readable_pairs]
        articles = [text for _, text in readable_pairs]
        total_article_chars = sum(len(article) for article in articles)
        if total_article_chars > self.settings.llm_source_review_max_chars:
            logger.info(
                "Fontes somam %d caracteres, acima do limite seguro de %d; não intervém",
                total_article_chars,
                self.settings.llm_source_review_max_chars,
            )
            return None

        model_input_limit = get_max_input_tokens(
            self.settings.llm_model_name, self.settings.llm_context_window_tokens
        )
        usable_context_tokens = max(
            4_000,
            model_input_limit - _SOURCE_REVIEW_RESERVED_TOKENS,
        )
        batch_budget_tokens = min(
            self.settings.llm_source_review_input_budget_tokens,
            usable_context_tokens,
        )
        batches = _build_source_batches(sources, articles, batch_budget_tokens)
        if len(batches) > self.settings.llm_source_review_max_batches:
            logger.info(
                "Revisão exigiria %d lotes, acima do limite seguro de %d; não intervém",
                len(batches),
                self.settings.llm_source_review_max_batches,
            )
            return None
        review_system = load_prompt("source_review", version=1).format(
            post_text=post.text,
            claim=verdict.claim,
        )
        source_reviews: list[str] = []
        for index, batch in enumerate(batches, start=1):
            logger.info("Revisando lote de fontes %d/%d", index, len(batches))
            review = await self.llm.complete(
                system=review_system,
                user=f"LOTE {index}/{len(batches)}:\n{batch}",
                purpose="source_review",
            )
            if not review.strip():
                logger.info("Lote de fontes sem revisão; não intervém")
                return None
            source_reviews.append(f"LOTE {index}/{len(batches)}:\n{review.strip()}")

        now = datetime.now(_BRASILIA)
        prompt = load_prompt("quote_post", version=2).format(
            current_datetime=f"{now:%d/%m/%Y %H:%M} (horário de Brasília)",
            post_text=post.text,
            claim=verdict.claim,
            rationale=verdict.rationale,
            tone=target_tone,
            sources=_format_sources(sources),
            source_reviews="\n\n".join(source_reviews),
        )

        logger.info("Gerando texto de intervenção após revisão integral das fontes...")
        generated_text = await self.llm.complete_with_tools(
            system=prompt,
            user="Use somente as revisões das fontes e gere o quote post.",
            tools=[],
            call_tool=_no_tool_call,
            max_tool_calls=_MAX_ARTICLE_READS,
            purpose="quote_post",
        )
        agent_output = generated_text
        generated_text, source_url = _parse_agent_output(agent_output, sources)
        if source_url is None:
            logger.info(
                "Agente de consulta vetou a intervenção em %s: fontes confirmam o post", post.uri
            )
            return None

        # Guardrails pós-geração (sobre o texto completo, antes de dividir em thread)
        generated_text = generated_text.strip()
        is_aggressive = any(term in generated_text.casefold() for term in _AGGRESSIVE_TERMS)
        if not generated_text or is_aggressive:
            logger.warning("Texto de intervenção reprovado pelos guardrails")
            return None

        # Quando o texto não cabe em um post só, continua como resposta
        # encadeada (thread) em vez de cortar o final com "…" -- cada pedaço
        # que não é o último termina com 🧵; o link da fonte vai só no último.
        chunks = _split_for_thread(generated_text)

        is_dry_run = getattr(self.settings, "intervention_dry_run", True)

        if is_dry_run:
            logger.info(
                "[DRY RUN] Intervenção gerada (não publicada, %d post(s)): %s | Fonte: %s",
                len(chunks),
                " | ".join(chunks),
                source_url,
            )
            return "dry_run_uri"

        logger.info("Publicando quote post para %s (%d post(s))...", post.uri, len(chunks))
        try:
            first_text = chunks[0] + (_THREAD_MARK if len(chunks) > 1 else "")
            first_source = source_url if len(chunks) == 1 else None
            root_uri, root_cid = await self.bsky_client.quote_post(
                target_uri=post.uri, target_cid=post.cid, text=first_text, source_url=first_source
            )
            self.repo.record_intervention(post.uri, post.author_did, "quote_post")

            parent_uri, parent_cid = root_uri, root_cid
            for index, chunk in enumerate(chunks[1:], start=1):
                is_last = index == len(chunks) - 1
                text = chunk if is_last else chunk + _THREAD_MARK
                source = source_url if is_last else None
                try:
                    parent_uri, parent_cid = await self.bsky_client.reply_post(
                        root_uri=root_uri,
                        root_cid=root_cid,
                        parent_uri=parent_uri,
                        parent_cid=parent_cid,
                        text=text,
                        source_url=source,
                    )
                except Exception as e:
                    logger.error(
                        "Falha ao publicar continuação %d/%d: %s", index + 1, len(chunks), e
                    )
                    break

            return root_uri
        except Exception as e:
            logger.error("Falha ao publicar quote post: %s", e)
            return None
