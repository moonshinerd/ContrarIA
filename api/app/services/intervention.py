import logging
import re
import unicodedata
from typing import Any

from app.clients.articles import fetch_article_text
from app.clients.bluesky_client import BlueskyClient
from app.core.config import get_settings
from app.domain.entities import Account, Evidence, Post, Verdict, VerdictLabel
from app.models.llm.base import LLMPort
from app.repositories.interventions import InterventionRepository
from app.services.prompts_loader import load_prompt

logger = logging.getLogger("contraria.services.intervention")

_AGGRESSIVE_TERMS = ("idiota", "burro", "imbecil", "estúpido", "estupido", "lixo")

_BLUESKY_LIMIT = 300
_THREAD_MARK = " 🧵"
_SOURCE_LABEL = " [Fonte]"

# Agente de consulta: o LLM vê a lista de fontes e abre na íntegra as que quiser.
_MAX_SOURCES_LISTED = 8
_MAX_ARTICLE_READS = 3
_ARTICLE_MAX_CHARS = 15000
_SOURCE_LINE = re.compile(r"\s*FONTE:\s*(\d+)[^\n]*\n?", re.IGNORECASE)
_READ_ARTICLE_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "ler_materia",
        "description": "Abre e devolve o texto completo de uma das fontes listadas.",
        "parameters": {
            "type": "object",
            "properties": {
                "numero": {"type": "integer", "description": "Número da fonte na lista."}
            },
            "required": ["numero"],
        },
    },
}


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


def _extract_source(text: str, sources: list[Evidence]) -> tuple[str, str | None]:
    """Separa a linha `FONTE: n` do texto; sem ela (ou inválida), cita a mais relevante.

    `FONTE: 0` é o veto do agente (as matérias confirmam o post): url None.
    """
    match = _SOURCE_LINE.match(text)
    if not match:
        return text, sources[0].url
    number = int(match.group(1))
    if number == 0:
        return "", None
    url = sources[number - 1].url if 1 <= number <= len(sources) else sources[0].url
    return text[match.end() :], url


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
        sources = verdict.evidences[:_MAX_SOURCES_LISTED]

        async def read_article(name: str, arguments: dict[str, Any]) -> str:
            number = arguments.get("numero")
            if name != "ler_materia" or not isinstance(number, int):
                return "Chamada inválida: use ler_materia com o número de uma fonte."
            if not 1 <= number <= len(sources):
                return f"Não existe fonte {number}; escolha entre 1 e {len(sources)}."
            source = sources[number - 1]
            logger.info("Agente de consulta lendo a fonte %d: %s", number, source.url)
            text = await fetch_article_text(source.url, max_chars=_ARTICLE_MAX_CHARS)
            return text or f"Não foi possível abrir a matéria. Trecho da busca: {source.snippet}"

        prompt = load_prompt("quote_post", version=2).format(
            post_text=post.text,
            claim=verdict.claim,
            rationale=verdict.rationale,
            tone=target_tone,
            sources=_format_sources(sources),
            max_reads=_MAX_ARTICLE_READS,
        )

        logger.info("Gerando texto de intervenção (LLM com consulta às fontes)...")
        generated_text = await self.llm.complete_with_tools(
            system=prompt,
            user="Consulte as fontes que precisar e gere o quote post.",
            tools=[_READ_ARTICLE_TOOL],
            call_tool=read_article,
            max_tool_calls=_MAX_ARTICLE_READS,
            purpose="quote_post",
        )
        generated_text, source_url = _extract_source(generated_text, sources)
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
