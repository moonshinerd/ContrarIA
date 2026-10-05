import asyncio
import json
import logging
import os
import time
from datetime import UTC, datetime, timedelta

import websockets
import yaml

from app.clients.bluesky_client import BlueskyClient
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


def _is_relevant(text: str) -> bool:
    text_lower = text.lower()
    return any(kw in text_lower for kw in POLITICAL_KEYWORDS)


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
    ):
        self.gate = gate
        self.repo = repo
        self.bsky_client = bsky_client
        self.poll_interval = poll_interval_seconds
        self.per_keyword_limit = per_keyword_limit

    async def poll_once(self) -> int:
        """Busca cada palavra-chave separadamente e grava os posts novos.

        O `searchPosts` não tem operador `OR`: ele vira mais um termo obrigatório,
        então uma query única com todas as palavras devolve zero resultados.
        """
        since = datetime.now(UTC) - timedelta(days=1)
        found: dict[str, dict] = {}
        for keyword in sorted(POLITICAL_KEYWORDS):
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
                found.setdefault(
                    p.uri,
                    {
                        "uri": p.uri,
                        "cid": p.cid,
                        "author_did": p.author_did,
                        "text": p.text,
                        "langs": p.langs,
                        "created_at": p.created_at,
                        "source": "search",
                    },
                )
        to_insert = list(found.values())
        if self.gate is not None:
            to_insert = to_insert[: self.gate.room()]
        if to_insert:
            self.repo.upsert_posts(to_insert)
            if self.gate is not None:
                self.gate.consume(len(to_insert))
        logger.info(
            "Foram inseridos %d de %d posts candidatos do searchPosts.", len(to_insert), len(found)
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
