"""Adapter do Bluesky (AT Protocol) sobre o SDK `atproto`.

Duas conexões com papéis diferentes:

- **AppView pública** (`bluesky_appview_url`): leituras sem login (getPosts,
  getProfile, getAuthorFeed). Não consome sessão nem a cota de login.
- **PDS autenticado** (`bluesky_pds_url`): searchPosts (a AppView pública
  devolve 403 sem login) e escritas (self-label, quote post em #14).

`createSession` tem limite de 30/5 min e 300/dia, então a sessão é
persistida em `bluesky_session_path` e reaproveitada. O SDK renova os tokens
sozinho, e cada renovação é gravada de novo pelo callback `on_session_change`.
Respostas 429 são repetidas respeitando o header `ratelimit-reset`.
"""

import asyncio
import logging
import os
import time
from collections.abc import Awaitable, Callable, Iterable
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, TypeVar

from atproto import AsyncClient, Session, SessionEvent, models
from atproto_client.exceptions import (
    BadRequestError,
    NetworkError,
    RateLimitExceededError,
    RequestErrorBase,
    UnauthorizedError,
)
from atproto_client.request import AsyncRequest

from app.core.config import Settings, get_settings
from app.domain.entities import Account, Post

logger = logging.getLogger("contraria.bluesky")

T = TypeVar("T")

GET_POSTS_BATCH = 25  # limite do app.bsky.feed.getPosts
SEARCH_PAGE_MAX = 100  # limite do app.bsky.feed.searchPosts
FEED_PAGE_MAX = 100  # limite do app.bsky.feed.getAuthorFeed
BOT_SELF_LABEL = "bot"
SESSION_ERRORS = {"ExpiredToken", "InvalidToken"}  # tokens da sessão não servem mais
RECORD_NOT_FOUND = "RecordNotFound"


class BlueskyAuthError(RuntimeError):
    """Credenciais ausentes ou inválidas para uma operação autenticada."""


def _xrpc_error(exc: RequestErrorBase) -> str | None:
    """Nome do erro XRPC devolvido pelo servidor (ex.: `ExpiredToken`), se houver."""
    return getattr(exc.response.content, "error", None) if exc.response else None


def _is_session_failure(exc: RequestErrorBase) -> bool:
    return isinstance(exc, UnauthorizedError) or (
        isinstance(exc, BadRequestError) and _xrpc_error(exc) in SESSION_ERRORS
    )


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _post_from_view(view: Any, *, is_repost: bool = False) -> Post:
    record = view.record
    created_at = _parse_datetime(getattr(record, "created_at", None))
    return Post(
        uri=view.uri,
        cid=view.cid,
        author_did=view.author.did,
        author_handle=view.author.handle,
        text=getattr(record, "text", "") or "",
        created_at=created_at or _parse_datetime(view.indexed_at),
        langs=list(getattr(record, "langs", None) or []),
        like_count=view.like_count or 0,
        repost_count=view.repost_count or 0,
        reply_count=view.reply_count or 0,
        quote_count=view.quote_count or 0,
        is_repost=is_repost,
    )


def _account_from_profile(profile: Any) -> Account:
    labels = profile.labels or []
    return Account(
        did=profile.did,
        handle=profile.handle,
        display_name=profile.display_name or "",
        description=profile.description or "",
        avatar_url=profile.avatar,
        created_at=_parse_datetime(profile.created_at),
        followers_count=profile.followers_count or 0,
        follows_count=profile.follows_count or 0,
        posts_count=profile.posts_count or 0,
        # self-label = rótulo emitido pela própria conta (src == did)
        self_labels=[label.val for label in labels if label.src == profile.did],
        labels=[label.val for label in labels],
    )


def _chunks(items: list[str], size: int) -> Iterable[list[str]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


class BlueskyClient:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        public_request: AsyncRequest | None = None,
        auth_request: AsyncRequest | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._settings = settings or get_settings()
        self._public = AsyncClient(
            base_url=self._settings.bluesky_appview_url, request=public_request
        )
        self._auth = self._new_auth_client(auth_request)
        self._logged_in = False
        self._login_lock = asyncio.Lock()
        self._sleep = sleep

    # ---- sessão ---------------------------------------------------------

    @property
    def _session_path(self) -> Path:
        return Path(self._settings.bluesky_session_path)

    async def _persist_session(self, event: SessionEvent, session: Session) -> None:
        path = self._session_path
        path.parent.mkdir(parents=True, exist_ok=True)
        # grava num temporário já com 0600 e troca de forma atômica: nunca há arquivo
        # legível por outros nem sessão pela metade para outro processo ler
        tmp = path.with_name(path.name + ".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as file:
            file.write(session.export())
        os.replace(tmp, path)
        logger.info("bluesky session persisted", extra={"event": event.value})

    def _new_auth_client(self, request: AsyncRequest | None = None) -> AsyncClient:
        client = AsyncClient(base_url=self._settings.bluesky_pds_url, request=request)
        client.on_session_change(self._persist_session)
        return client

    def _discard_session(self) -> None:
        """Esquece a sessão atual (memória e arquivo) para forçar um novo createSession.

        O SDK não permite limpar a sessão de um cliente, então cria-se outro sobre o mesmo
        transporte HTTP.
        """
        self._auth = self._new_auth_client(self._auth.request)
        self._logged_in = False
        self._session_path.unlink(missing_ok=True)

    async def login(self) -> str:
        """Garante uma sessão autenticada e devolve o DID da conta do bot.

        Reaproveita a sessão persistida; só chama createSession se não houver
        sessão salva ou se ela tiver sido revogada.
        """
        async with self._login_lock:
            if self._logged_in:
                return self._auth.me.did if self._auth.me else self._did_from_session()

            path = self._session_path
            if path.exists():
                try:
                    await self._auth.login(
                        session_string=path.read_text().strip(), fetch_bsky_profile=False
                    )
                    self._logged_in = True
                    logger.info("bluesky session resumed")
                    return self._did_from_session()
                except (UnauthorizedError, ValueError):
                    logger.warning("stored bluesky session rejected; creating a new one")

            handle, password = self._settings.bluesky_handle, self._settings.bluesky_app_password
            if not handle or not password:
                raise BlueskyAuthError(
                    "BLUESKY_HANDLE e BLUESKY_APP_PASSWORD precisam estar no api/.env "
                    "para operações autenticadas"
                )
            await self._auth.login(login=handle, password=password, fetch_bsky_profile=False)
            self._logged_in = True
            logger.info("bluesky session created", extra={"handle": handle})
            return self._did_from_session()

    def _did_from_session(self) -> str:
        session = self._auth._session  # noqa: SLF001 -- o SDK não expõe o DID de outra forma
        if session is None:
            raise BlueskyAuthError("sessão ausente após login")
        return session.did

    # ---- rate limit -----------------------------------------------------

    async def _call(self, fn: Callable[[], Awaitable[T]]) -> T:
        """Executa a chamada repetindo em 429 (até o `ratelimit-reset`) e em falha de rede."""
        max_retries = self._settings.bluesky_max_retries
        for attempt in range(max_retries + 1):
            try:
                return await fn()
            except RateLimitExceededError as exc:
                if attempt == max_retries:
                    raise
                wait = self._retry_after(exc)
                logger.warning(
                    "bluesky rate limited", extra={"wait_seconds": wait, "attempt": attempt + 1}
                )
                await self._sleep(wait)
            except NetworkError:
                if attempt == max_retries:
                    raise
                await self._sleep(min(2**attempt, self._settings.bluesky_max_backoff_seconds))
        raise AssertionError("unreachable")

    async def _authenticated(self, fn: Callable[[], Awaitable[T]]) -> T:
        """Como `_call`, mas garante login e se recupera de sessão revogada ou expirada.

        Retomar a sessão salva não valida nada na rede (`fetch_bsky_profile=False`), então
        um refresh token vencido só aparece aqui. Descarta a sessão, refaz o login com o
        App Password e repete a chamada uma única vez.
        """
        await self.login()
        try:
            return await self._call(fn)
        except (UnauthorizedError, BadRequestError) as exc:
            if not _is_session_failure(exc):
                raise
            logger.warning("bluesky session rejected mid-call; logging in again")
            self._discard_session()
            await self.login()
            return await self._call(fn)

    def _retry_after(self, exc: RateLimitExceededError) -> float:
        headers = {k.lower(): v for k, v in (exc.response.headers if exc.response else {}).items()}
        reset = headers.get("ratelimit-reset")
        wait = 1.0
        if reset is not None:
            try:
                wait = max(float(reset) - time.time(), 1.0)
            except ValueError:
                pass
        return min(wait, self._settings.bluesky_max_backoff_seconds)

    # ---- leitura pública ------------------------------------------------

    async def get_posts(self, uris: list[str]) -> list[Post]:
        """Hidrata posts com contadores de engajamento, em lotes de 25."""
        posts: list[Post] = []
        for batch in _chunks(list(dict.fromkeys(uris)), GET_POSTS_BATCH):
            response = await self._call(
                lambda b=batch: self._public.app.bsky.feed.get_posts({"uris": b})
            )
            posts.extend(_post_from_view(view) for view in response.posts)
        return posts

    async def get_profile(self, actor: str) -> Account:
        profile = await self._call(
            lambda: self._public.app.bsky.actor.get_profile({"actor": actor})
        )
        return _account_from_profile(profile)

    async def get_author_feed(self, actor: str, *, limit: int = 100) -> list[Post]:
        """Últimos `limit` itens do autor (posts e reposts), paginando se preciso."""
        posts: list[Post] = []
        cursor: str | None = None
        while len(posts) < limit:
            params = {
                "actor": actor,
                "limit": min(FEED_PAGE_MAX, limit - len(posts)),
                "cursor": cursor,
            }
            response = await self._call(
                lambda p=params: self._public.app.bsky.feed.get_author_feed(p)
            )
            for item in response.feed:
                is_repost = isinstance(item.reason, models.AppBskyFeedDefs.ReasonRepost)
                posts.append(_post_from_view(item.post, is_repost=is_repost))
            cursor = response.cursor
            if not cursor or not response.feed:
                break
        return posts[:limit]

    # ---- autenticado ----------------------------------------------------

    async def search_posts(
        self,
        query: str,
        *,
        lang: str | None = "pt",
        sort: Literal["top", "latest"] = "latest",
        since: datetime | None = None,
        limit: int = 25,
    ) -> list[Post]:
        """Busca posts (exige login). Pagina até `limit` resultados."""
        posts: list[Post] = []
        cursor: str | None = None
        while len(posts) < limit:
            params = {
                "q": query,
                "lang": lang,
                "sort": sort,
                "since": since.isoformat() if since else None,
                "limit": min(SEARCH_PAGE_MAX, limit - len(posts)),
                "cursor": cursor,
            }
            response = await self._authenticated(
                lambda p=params: self._auth.app.bsky.feed.search_posts(p)
            )
            posts.extend(_post_from_view(view) for view in response.posts)
            cursor = response.cursor
            if not cursor or not response.posts:
                break
        return posts[:limit]

    async def ensure_bot_self_label(self) -> bool:
        """Aplica o self-label `bot` no perfil do bot. Devolve True se alterou algo.

        Recomendação da doc de bots do Bluesky. Preserva os demais campos do perfil.
        """
        did = await self.login()
        collection, rkey = "app.bsky.actor.profile", "self"
        swap_cid: str | None = None  # só sobrescreve se o record não mudou desde a leitura
        try:
            current = await self._authenticated(
                lambda: self._auth.com.atproto.repo.get_record(
                    {"repo": did, "collection": collection, "rkey": rkey}
                )
            )
            record: dict[str, Any] = models.get_model_as_dict(current.value)
            swap_cid = current.cid
        except BadRequestError as exc:
            # Só "perfil ainda sem record" cria do zero. Qualquer outra falha (rede,
            # auth, rate limit) sobe: gravar um record vazio apagaria nome, bio e avatar.
            if _xrpc_error(exc) != RECORD_NOT_FOUND:
                raise
            record = {"$type": collection}

        values = (record.get("labels") or {}).get("values") or []
        if any(v.get("val") == BOT_SELF_LABEL for v in values):
            return False
        record["labels"] = {
            "$type": "com.atproto.label.defs#selfLabels",
            "values": [*values, {"val": BOT_SELF_LABEL}],
        }
        data: dict[str, Any] = {"repo": did, "collection": collection, "rkey": rkey}
        data["record"] = record
        if swap_cid:
            data["swapRecord"] = swap_cid
        await self._authenticated(lambda: self._auth.com.atproto.repo.put_record(data))
        return True

    async def quote_post(
        self, target_uri: str, target_cid: str, text: str, source_url: str | None = None
    ) -> str:
        """Cria um quote post para o alvo com o texto fornecido (e link opcional)."""
        await self.login()

        from atproto import client_utils, models

        tb = client_utils.TextBuilder()
        tb.text(text)
        if source_url:
            tb.text(" ")
            tb.link("[Fonte]", source_url)

        # O embed deve ser um embed record apontando pro alvo
        embed = models.AppBskyEmbedRecord.Main(
            record=models.ComAtprotoRepoStrongRef.Main(uri=target_uri, cid=target_cid)
        )

        response = await self._authenticated(lambda: self._auth.send_post(text=tb, embed=embed))
        return response.uri

    async def has_postgate_quote_disabled(self, post_uri: str) -> bool:
        """Verifica se o autor do post desabilitou citações via postgate."""
        parts = post_uri.split("/")
        if len(parts) < 3:
            return False
        did = parts[2]
        rkey = parts[-1]
        try:
            current = await self._call(
                lambda: self._public.com.atproto.repo.get_record(
                    {"repo": did, "collection": "app.bsky.feed.postgate", "rkey": rkey}
                )
            )
            from atproto import models

            record = models.get_model_as_dict(current.value)
            rules = record.get("embeddingRules", [])
            for rule in rules:
                if rule.get("$type") == "app.bsky.feed.postgate#disableRule":
                    return True
        except Exception:
            return False
        return False

    async def close(self) -> None:
        await self._public.request.close()
        await self._auth.request.close()
