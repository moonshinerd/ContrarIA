import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta

import websockets

from app.clients.bluesky_client import BlueskyClient
from app.repositories.posts import PostRepository

logger = logging.getLogger("contraria.collector")

POLITICAL_KEYWORDS = {
    "política",
    "eleição",
    "eleicao",
    "governo",
    "presidente",
    "urna",
    "voto",
    "stf",
    "deputado",
    "senador",
    "candidato",
    "prefeito",
    "vereador",
}


def _is_relevant(text: str) -> bool:
    text_lower = text.lower()
    return any(kw in text_lower for kw in POLITICAL_KEYWORDS)


class JetstreamConsumer:
    def __init__(
        self,
        repo: PostRepository,
        stream_url: str = "wss://jetstream2.us-east.bsky.network/subscribe?wantedCollections=app.bsky.feed.post",
    ):
        self.repo = repo
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
        if not langs or "pt" not in langs:
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
        cursor = self.repo.get_cursor("jetstream")
        if cursor > 0:
            cursor = max(0, cursor - 5_000_000)

        url = self.stream_url
        if cursor > 0:
            url += f"&cursor={cursor}"

        import ssl

        import certifi

        ssl_context = ssl.create_default_context(cafile=certifi.where())

        while True:
            try:
                async with websockets.connect(url, ssl=ssl_context) as ws:
                    logger.info("Conectado ao Jetstream em %s", url)
                    while True:
                        msg = await ws.recv()
                        post_data = self.parse_message(msg)
                        if post_data:
                            time_us = post_data.pop("time_us", None)
                            self.repo.upsert_posts([post_data])
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
        self, repo: PostRepository, bsky_client: BlueskyClient, poll_interval_seconds: int = 600
    ):
        self.repo = repo
        self.bsky_client = bsky_client
        self.poll_interval = poll_interval_seconds

    async def run(self):
        while True:
            try:
                logger.info("Iniciando busca de posts por searchPosts...")
                # Buscar posts das últimas 24 horas
                since = datetime.now(UTC) - timedelta(days=1)
                query = " OR ".join(POLITICAL_KEYWORDS)

                posts = await self.bsky_client.search_posts(
                    query=query, lang="pt", sort="top", since=since, limit=50
                )

                posts_data = []
                for p in posts:
                    posts_data.append(
                        {
                            "uri": p.uri,
                            "cid": p.cid,
                            "author_did": p.author_did,
                            "text": p.text,
                            "langs": p.langs,
                            "created_at": p.created_at,
                            "source": "search",
                        }
                    )

                if posts_data:
                    self.repo.upsert_posts(posts_data)
                    logger.info(
                        "Foram inseridos %d posts candidatos do searchPosts.", len(posts_data)
                    )

            except Exception as e:
                logger.error("Erro no SearchPoller: %s", e)

            await asyncio.sleep(self.poll_interval)
