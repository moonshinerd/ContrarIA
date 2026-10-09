import asyncio
import json
import logging
import os
import re
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import websockets
import yaml

from app.clients.bluesky_client import BlueskyClient
from app.core.config import get_settings
from app.domain.prioritization import calculate_relevance
from app.repositories.posts import PostRepository

logger = logging.getLogger("contraria.collector")

TOPICS_FILE = os.path.join(os.path.dirname(__file__), "..", "domain", "topics", "politica.yaml")
with open(TOPICS_FILE, encoding="utf-8") as f:
    _topic_data = yaml.safe_load(f)
    POLITICAL_KEYWORDS = set(_topic_data.get("keywords", []))


class IngestGate:
    """Contrapressão da coleta: só deixa entrar posts enquanto a fila tem vaga.

    Cheia a fila (`max_pending`), os posts novos são descartados em vez de guardados,
    para a análise nunca processar posts velhos. A contagem vem do banco no máximo a cada
    `refresh_seconds`; entre as leituras, o que já entrou é somado localmente.
    """

    def __init__(
        self,
        repo: PostRepository,
        max_pending: int,
        refresh_seconds: float = 2.0,
        search_reserve: int = 0,
    ):
        self.repo = repo
        self.max_pending = max_pending
        # Vagas que o Jetstream não pode ocupar: ficam para o searchPosts, cujos posts são
        # os de maior alcance (ordenados por `top`). Sem a reserva, o firehose enche a fila
        # antes de cada ciclo do poller.
        self.search_reserve = min(search_reserve, max_pending)
        self.refresh_seconds = refresh_seconds
        self._pending = 0
        self._checked_at = float("-inf")

    def room(self, *, stream: bool = False) -> int:
        """Vagas livres. Com `stream=True` (Jetstream), desconta a reserva do searchPosts."""
        if self.max_pending <= 0:
            return 1 << 30
        now = time.monotonic()
        if now - self._checked_at >= self.refresh_seconds:
            self._pending = self.repo.pending_count()
            self._checked_at = now
        limit = self.max_pending - (self.search_reserve if stream else 0)
        return max(0, limit - self._pending)

    def consume(self, n: int = 1) -> None:
        self._pending += n

    def invalidate(self) -> None:
        """Descarta a contagem em cache (após inserir em massa ou podar a fila)."""
        self._checked_at = float("-inf")


def _is_relevant(text: str) -> bool:
    text_lower = text.lower()
    return any(kw in text_lower for kw in POLITICAL_KEYWORDS)


_FACTCHECK_PREFIXES = re.compile(
    r"^(?:fact[ -]?check|checagem|é falso que|é fake que|boato:|verificação:)\s*",
    re.IGNORECASE,
)


def _claim_query(article: dict[str, str], *, max_chars: int = 140) -> str | None:
    """Transforma o título de uma checagem em uma consulta curta e específica.

    Títulos de verificadores normalmente carregam a alegação. Removemos apenas
    o rótulo editorial e preservamos a frase, em vez de inferir uma nova claim.
    """
    title = " ".join(article.get("title", "").split())
    title = _FACTCHECK_PREFIXES.sub("", title).strip(" .:-–—")
    if len(title) < 12:
        return None
    return title[:max_chars].rsplit(" ", 1)[0] if len(title) > max_chars else title


class JetstreamConsumer:
    def __init__(
        self,
        repo: PostRepository,
        stream_url: str = "wss://jetstream2.us-east.bsky.network/subscribe?wantedCollections=app.bsky.feed.post",
        gate: "IngestGate | None" = None,
    ):
        self.repo = repo
        self.gate = gate
        self.stream_url = stream_url

    def parse_message(self, msg: str) -> dict | None:
        data = json.loads(msg)
        if data.get("kind") != "commit":
            return None

        commit = data.get("commit", {})
        if commit.get("operation") != "create":
            return None

        record = commit.get("record", {})
        langs = record.get("langs", [])
        if not any(lang.casefold().startswith("pt") for lang in langs if isinstance(lang, str)):
            return None

        text = record.get("text", "")
        if not _is_relevant(text):
            return None

        did = data.get("did")
        rkey = commit.get("rkey")
        if not did or not rkey:
            return None

        uri = f"at://{did}/app.bsky.feed.post/{rkey}"

        created_at_str = record.get("createdAt")
        try:
            if created_at_str:
                created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
            else:
                created_at = datetime.now(UTC)
        except Exception:
            created_at = datetime.now(UTC)

        return {
            "uri": uri,
            "cid": commit.get("cid", ""),
            "author_did": did,
            "text": text,
            "langs": langs,
            "created_at": created_at,
            "source": "jetstream",
            "time_us": data.get("time_us"),
        }

    async def run(self):
        import ssl

        import certifi

        ssl_context = ssl.create_default_context(cafile=certifi.where())

        while True:
            try:
                cursor = self.repo.get_cursor("jetstream")
                if cursor > 0:
                    cursor = max(0, cursor - 5_000_000)
                url = self.stream_url
                if cursor > 0:
                    url += f"&cursor={cursor}"
                async with websockets.connect(url, ssl=ssl_context) as ws:
                    logger.info("Conectado ao Jetstream em %s", url)
                    while True:
                        msg = await ws.recv()
                        post_data = self.parse_message(msg)
                        time_us = json.loads(msg).get("time_us")
                        if post_data:
                            post_data.pop("time_us", None)
                            # Fila cheia: descarta (o cursor segue andando; só entra post fresco).
                            if self.gate is None or self.gate.room(stream=True) > 0:
                                self.repo.upsert_posts([post_data])
                                if self.gate is not None:
                                    self.gate.consume()
                        if time_us:
                            self.repo.set_cursor("jetstream", time_us)

            except websockets.exceptions.ConnectionClosed:
                logger.warning("Conexão Jetstream fechada, reconectando em 5s...")
                await asyncio.sleep(5)
            except Exception as e:
                logger.error("Erro inesperado no Jetstream: %s", e)
                await asyncio.sleep(5)


class SearchPoller:
    def __init__(
        self,
        repo: PostRepository,
        bsky_client: BlueskyClient,
        poll_interval_seconds: int = 600,
        per_keyword_limit: int = 25,
        gate: "IngestGate | None" = None,
        fact_articles: Any | None = None,
    ):
        self.gate = gate
        self.repo = repo
        self.bsky_client = bsky_client
        self.poll_interval = poll_interval_seconds
        self.per_keyword_limit = per_keyword_limit
        self.fact_articles = fact_articles

    def _factcheck_queries(self) -> list[str]:
        """Consultas prioritárias, deduplicadas, derivadas de checagens recentes."""
        settings = get_settings()
        if not settings.factcheck_search_enabled:
            return []
        queries = list(settings.factcheck_search_static_queries)
        if self.fact_articles is not None:
            try:
                articles = self.fact_articles.recent_for_collection(
                    limit=settings.factcheck_search_max_articles,
                    max_age_days=settings.factcheck_search_max_age_days,
                )
                queries.extend(query for article in articles if (query := _claim_query(article)))
            except Exception as exc:
                # A busca política genérica continua funcionando se a base RSS falhar.
                logger.warning("Não foi possível obter checagens para busca ativa: %s", exc)
        unique: list[str] = []
        for query in queries:
            normalized = " ".join(query.split())
            if normalized and normalized.casefold() not in {item.casefold() for item in unique}:
                unique.append(normalized)
        return unique[: settings.factcheck_search_max_queries]

    async def poll_once(self) -> int:
        """Busca cada palavra-chave separadamente e grava os posts novos.

        O `searchPosts` não tem operador `OR`: ele vira mais um termo obrigatório,
        então uma query única com todas as palavras devolve zero resultados.
        """
        since = datetime.now(UTC) - timedelta(days=1)
        found: dict[str, dict] = {}
        # Busca guiada vem primeiro e ganha prioridade na fila. A verificação
        # continua idêntica: entrar aqui não significa que o post será rotulado
        # nem respondido.
        factcheck_queries = self._factcheck_queries()
        query_plan = [(query, "factcheck_search") for query in factcheck_queries]
        query_plan.extend((keyword, "search") for keyword in sorted(POLITICAL_KEYWORDS))
        settings = get_settings()
        for keyword, source in query_plan:
            try:
                posts = await self.bsky_client.search_posts(
                    query=keyword,
                    lang="pt",
                    sort="top",
                    since=since,
                    limit=self.per_keyword_limit,
                )
            except Exception as e:
                logger.error("Erro no searchPosts para %r: %s", keyword, e)
                continue
            for p in posts:
                priority = calculate_relevance(
                    likes=getattr(p, "like_count", 0),
                    reposts=getattr(p, "repost_count", 0),
                    replies=getattr(p, "reply_count", 0),
                    quotes=getattr(p, "quote_count", 0),
                    velocity=0.0,
                    followers=0,
                )
                if source == "factcheck_search":
                    priority += settings.factcheck_search_priority_bonus
                candidate = {
                    "uri": p.uri,
                    "cid": p.cid,
                    "author_did": p.author_did,
                    "text": p.text,
                    "langs": p.langs,
                    "created_at": p.created_at,
                    "source": source,
                    "triage_status": "monitor",
                    "priority": priority,
                }
                # Um resultado vindo da busca guiada prevalece sobre a genérica.
                existing = found.get(p.uri)
                if existing is None or candidate["priority"] > existing["priority"]:
                    found[p.uri] = candidate
        # O searchPosts devolve a cada ciclo muitos posts populares que já temos: só os novos
        # contam (e só eles ocupam vaga da fila).
        known = self.repo.existing_uris(list(found))
        to_insert = [post for uri, post in found.items() if uri not in known]
        # Prioridade por popularidade já na entrada: sem ela o post ficava sem nota até o refresh
        # de engajamento e não dava para compará-lo com os que já estão na fila.
        to_insert.sort(key=lambda post: post["priority"], reverse=True)
        max_pending = self.gate.max_pending if self.gate is not None else 0
        if max_pending > 0:
            # Reserva explícita para republicações de alegações checadas. Sem
            # isso, uma onda de posts políticos muito populares poderia ocupar
            # todas as vagas antes que a busca guiada fosse considerada.
            reserve = min(settings.factcheck_search_reserve, max_pending)
            guided = [post for post in to_insert if post["source"] == "factcheck_search"]
            ordinary = [post for post in to_insert if post["source"] != "factcheck_search"]
            selected_guided = guided[:reserve]
            selected_ordinary = ordinary[: max_pending - len(selected_guided)]
            to_insert = sorted(
                selected_guided + selected_ordinary,
                key=lambda post: post["priority"],
                reverse=True,
            )
        if to_insert:
            self.repo.upsert_posts(to_insert)
        if max_pending > 0:
            # Fila cheia: os mais populares entram e os menos badalados saem (viram 'expired').
            evicted = self.repo.trim_pending(max_pending)
            if evicted:
                logger.info(
                    "Fila acima do teto de %d: %d expirados por menor prioridade",
                    max_pending,
                    evicted,
                )
            self.gate.invalidate()
        elif self.gate is not None and to_insert:
            self.gate.consume(len(to_insert))
        logger.info(
            "searchPosts: %d novos inseridos de %d encontrados "
            "(%d já conhecidos; %d consultas guiadas).",
            len(to_insert),
            len(found),
            len(known),
            len(factcheck_queries),
        )
        return len(to_insert)

    async def run(self):
        while True:
            try:
                logger.info("Iniciando busca de posts por searchPosts...")
                await self.poll_once()
            except Exception as e:
                logger.error("Erro no SearchPoller: %s", e)
            await asyncio.sleep(self.poll_interval)
