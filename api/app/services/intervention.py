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
_SOURCE_LABEL = " [1] [2] [3]"

_BRASILIA = timezone(timedelta(hours=-3))

# A revisão lê as cinco fontes mais relevantes por inteiro. Quando o conjunto
# excede a janela de entrada, o texto é dividido em lotes sem descartar trechos.
_MAX_SOURCES_LISTED = 5
_MAX_ARTICLE_READS = 0
_CHARS_PER_TOKEN_ESTIMATE = 3
_SOURCE_REVIEW_RESERVED_TOKENS = 16_000
_TYPE_LINE = re.compile(r"\s*TIPO:\s*(\w+)[^\n]*\n?", re.IGNORECASE)
_VERDICT_LINE = re.compile(r"\s*VEREDITO:\s*(\w+)[^\n]*\n?", re.IGNORECASE)
_SOURCE_LINE = re.compile(r"\s*FONTE:\s*([0-9, ]+)[^\n]*\n?", re.IGNORECASE)
_ACTIONABLE_VERDICTS = {"DESMENTE", "DISTORCE"}


_PROPER_NAME_REGEX = re.compile(
    r"\b[A-ZÁÀÂÃÉÊÍÓÔÕÚÇ][a-záàâãéêíóôõúç]+(?:\s+(?:d[aeo]s?\s+)?[A-ZÁÀÂÃÉÊÍÓÔÕÚÇ][a-záàâãéêíóôõúç]+)+\b"
)
_COMMON_NAME_EXCEPTIONS = {
    "o post",
    "a postagem",
    "as fontes",
    "a fonte",
    "o autor",
    "a autora",
    "de acordo",
    "no brasil",
    "do brasil",
    "o brasil",
    "minas gerais",
    "são paulo",
    "espírito santo",
    "mato grosso",
    "rio de janeiro",
    "estados unidos",
    "américa latina",
}

_PORTUGUESE_STOPWORDS = frozenset(
    "a o os as um uma uns umas de do da dos das em no na nos nas por para com sem "
    "sobre pelo pela pelos pelas que se como quando onde porque qual quem este esta "
    "esse essa aquele aquela isto isso aquilo ele ela eles elas seu sua seus suas "
    "foi foram era eram ser é são ter teve tinham mais menos muito pouco todo toda".split()
)


def _find_hallucinated_entity(generated_text: str, source_text: str) -> str | None:
    """Detecta menções a nomes próprios na intervenção que não aparecem no post original."""
    source_lower = source_text.casefold()
    for match in _PROPER_NAME_REGEX.finditer(generated_text):
        name = match.group(0).strip()
        if name.casefold() in _COMMON_NAME_EXCEPTIONS:
            continue
        first_token = name.split()[0].casefold()
        if first_token not in source_lower:
            return name
    return None


def _is_claim_relevant_to_post(claim: str, post_text: str) -> bool:
    """Verifica se a claim possui palavras informativas em comum com o texto do post."""
    if len(claim.strip()) <= 5 or len(post_text.strip()) <= 5:
        return True
    claim_informative = {
        w.casefold()
        for w in re.findall(r"\w{4,}", claim)
        if w.casefold() not in _PORTUGUESE_STOPWORDS
    }
    post_words = {
        w.casefold()
        for w in re.findall(r"\w{4,}", post_text)
        if w.casefold() not in _PORTUGUESE_STOPWORDS
    }
    if not claim_informative or not post_words:
        return True
    return bool(claim_informative & post_words)


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


def _parse_agent_output(text: str, sources: list[Evidence]) -> tuple[str, list[str]]:
    """Lê `TIPO:`, `VEREDITO:` e `FONTE: n, m` e devolve (texto, lista de urls das fontes).

    urls vazia = não publicar: o post é opinião/previsão (TIPO: OPINIAO), o
    agente concluiu CONFIRMA, ou não seguiu o formato (na dúvida, não responde).
    """
    claim_type = _TYPE_LINE.match(text)
    if not claim_type or claim_type.group(1).upper() != "FATO":
        return "", []
    text = text[claim_type.end() :]
    verdict = _VERDICT_LINE.match(text)
    if not verdict or verdict.group(1).upper() not in _ACTIONABLE_VERDICTS:
        return "", []
    rest = text[verdict.end() :]
    source_match = _SOURCE_LINE.match(rest)
    if not source_match:
        return rest, [sources[0].url] if sources else []
    raw_numbers = [x.strip() for x in source_match.group(1).split(",") if x.strip().isdigit()]
    numbers = [int(x) for x in raw_numbers]
    if not numbers or 0 in numbers:
        return "", []
    urls: list[str] = []
    for num in numbers:
        if 1 <= num <= len(sources):
            u = sources[num - 1].url
            if u not in urls:
                urls.append(u)
    if not urls and sources:
        urls.append(sources[0].url)
    return rest[source_match.end() :], urls[:3]


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

    async def _validate_semantic_coherence(
        self, post_text: str, generated_text: str, claim: str
    ) -> tuple[bool, str]:
        """Audita semanticamente via LLM se a pergunta socrática gerada é pertinente

        ao que o autor do post realmente afirmou, garantindo que não atribui ao post
        fatos, pessoas ou alegações ausentes trazidos apenas pelas fontes externas.
        """
        if not getattr(self.settings, "enable_semantic_critic", True):
            return True, "Auditoria semântica desabilitada por configuração"

        try:
            critic_prompt = load_prompt("semantic_critic", version=1).format(
                post_text=post_text,
                claim=claim,
                generated_text=generated_text,
            )
            response = await self.llm.complete(
                system=critic_prompt,
                user="Avalie a intervenção proposta segundo as regras e retorne DECISAO e MOTIVO.",
                purpose="critic_coherence",
            )
            text = response.strip()
            if "REPROVADA" in text.upper():
                lines = [line.strip() for line in text.splitlines() if line.strip()]
                reason_line = next((line for line in lines if "MOTIVO:" in line.upper()), "")
                reason = (
                    reason_line.replace("MOTIVO:", "").strip()
                    if reason_line
                    else "Inconsistência semântica apontada pelo auditor"
                )
                return False, reason

            return True, "Intervenção aprovada pelo auditor semântico"
        except Exception as e:
            logger.warning("Falha ao executar auditor semântico: %s; prosseguindo com cautela", e)
            return True, "Auditoria semântica indisponível"

    async def execute_intervention(
        self, post: Post, author: Account, verdict: Verdict, bot_score: float
    ) -> str | None:
        if not await self._should_intervene(post, author, verdict):
            return None

        # Alinhamento da claim com o post original: a claim precisa ter pertinência com o post a ser citado.
        if not _is_claim_relevant_to_post(verdict.claim, post.text):
            logger.warning(
                "Intervenção abortada: alegação '%s' não possui correspondência temática com o post original %s",
                verdict.claim,
                post.uri,
            )
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
        generated_text, source_urls = _parse_agent_output(agent_output, sources)
        if not source_urls:
            logger.info(
                "Agente de consulta vetou a intervenção em %s: fontes confirmam o post", post.uri
            )
            return None

        # Guardrails pós-geração (sobre o texto completo, antes de dividir em thread)
        generated_text = generated_text.strip()
        is_aggressive = any(term in generated_text.casefold() for term in _AGGRESSIVE_TERMS)
        if not generated_text or is_aggressive:
            logger.warning("Texto de intervenção reprovado pelos guardrails de agressividade")
            return None

        # Validação de pertinência socrática e grounding semântico via LLM (Critic)
        is_coherent, critic_reason = await self._validate_semantic_coherence(
            post.text, generated_text, verdict.claim
        )
        if not is_coherent:
            logger.warning(
                "Intervenção vetada pelo auditor semântico: %s (post: %s)",
                critic_reason,
                post.uri,
            )
            return None

        hallucinated_name = _find_hallucinated_entity(generated_text, post.text)
        if hallucinated_name:
            logger.warning(
                "Intervenção vetada pelo guardrail de grounding: entidade '%s' ausente do post original %s",
                hallucinated_name,
                post.uri,
            )
            return None

        # Quando o texto não cabe em um post só, continua como resposta
        # encadeada (thread) em vez de cortar o final com "…" -- cada pedaço
        # que não é o último termina com 🧵; o link da fonte vai só no último.
        chunks = _split_for_thread(generated_text)

        is_dry_run = getattr(self.settings, "intervention_dry_run", True)

        if is_dry_run:
            logger.info(
                "[DRY RUN] Intervenção gerada (não publicada, %d post(s)): %s | Fontes: %s",
                len(chunks),
                " | ".join(chunks),
                ", ".join(source_urls),
            )
            return "dry_run_uri"

        logger.info("Publicando quote post para %s (%d post(s))...", post.uri, len(chunks))
        try:
            first_text = chunks[0] + (_THREAD_MARK if len(chunks) > 1 else "")
            first_sources = source_urls if len(chunks) == 1 else None
            first_source = first_sources[0] if first_sources else None
            root_uri, root_cid = await self.bsky_client.quote_post(
                target_uri=post.uri,
                target_cid=post.cid,
                text=first_text,
                source_url=first_source,
                source_urls=first_sources,
            )
            self.repo.record_intervention(post.uri, post.author_did, "quote_post")

            parent_uri, parent_cid = root_uri, root_cid
            for index, chunk in enumerate(chunks[1:], start=1):
                is_last = index == len(chunks) - 1
                text = chunk if is_last else chunk + _THREAD_MARK
                sources_to_pass = source_urls if is_last else None
                source_to_pass = sources_to_pass[0] if sources_to_pass else None
                try:
                    parent_uri, parent_cid = await self.bsky_client.reply_post(
                        root_uri=root_uri,
                        root_cid=root_cid,
                        parent_uri=parent_uri,
                        parent_cid=parent_cid,
                        text=text,
                        source_url=source_to_pass,
                        source_urls=sources_to_pass,
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
