"""Testes do BlueskyClient com respostas HTTP mockadas (httpx.MockTransport)."""

import base64
import json
import time
from pathlib import Path

import httpx
import pytest
from atproto_client.request import AsyncRequest

from app.clients.bluesky_client import BlueskyAuthError, BlueskyClient
from app.core.config import Settings

FIXTURES = Path(__file__).parent / "fixtures" / "bluesky"


def _jwt(exp_offset: int = 3600) -> str:
    def b64(data: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(data).encode()).decode().rstrip("=")

    now = int(time.time())
    payload = {
        "sub": "did:plc:contraria",
        "scope": "com.atproto.appPass",
        "iat": now,
        "exp": now + exp_offset,
    }
    return f"{b64({'alg': 'HS256', 'typ': 'JWT'})}.{b64(payload)}.sig"


def _post_view(n: int, did: str = "did:plc:author") -> dict:
    return {
        "uri": f"at://{did}/app.bsky.feed.post/{n}",
        "cid": f"bafy{n}",
        "author": {"did": did, "handle": "autor.bsky.social"},
        "record": {
            "$type": "app.bsky.feed.post",
            "text": f"post {n} sobre a urna eletrônica",
            "createdAt": "2026-09-16T10:00:00.000Z",
            "langs": ["pt"],
        },
        "indexedAt": "2026-09-16T10:00:01.000Z",
        "likeCount": n,
        "repostCount": 2 * n,
        "replyCount": 1,
        "quoteCount": 0,
    }


class Router:
    """Roteia requisições por NSID e registra as chamadas feitas."""

    def __init__(self) -> None:
        self.handlers: dict[str, list] = {}
        self.calls: list[httpx.Request] = []

    def on(self, nsid: str, *responses: httpx.Response) -> None:
        self.handlers.setdefault(nsid, []).extend(responses)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        nsid = request.url.path.rsplit("/", 1)[-1]
        queue = self.handlers.get(nsid)
        if not queue:
            return httpx.Response(404, json={"error": "NotMocked", "message": nsid})
        return queue.pop(0) if len(queue) > 1 else queue[0]

    def called(self, nsid: str) -> list[httpx.Request]:
        return [c for c in self.calls if c.url.path.endswith(nsid)]


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        bluesky_handle="contraria.bsky.social",
        bluesky_app_password="xxxx-xxxx-xxxx-xxxx",
        bluesky_session_path=str(tmp_path / "bluesky.session"),
    )


@pytest.fixture
def router() -> Router:
    return Router()


@pytest.fixture
def sleeps() -> list[float]:
    return []


@pytest.fixture
def client(settings: Settings, router: Router, sleeps: list[float]) -> BlueskyClient:
    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    transport = httpx.MockTransport(router)
    return BlueskyClient(
        settings,
        public_request=AsyncRequest(transport=transport),
        auth_request=AsyncRequest(transport=transport),
        sleep=fake_sleep,
    )


def _session_response() -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "did": "did:plc:contraria",
            "handle": "contraria.bsky.social",
            "accessJwt": _jwt(),
            "refreshJwt": _jwt(86400),
            "active": True,
        },
    )


async def test_get_posts_batches_by_25_and_maps_engagement(
    client: BlueskyClient, router: Router
) -> None:
    router.on(
        "app.bsky.feed.getPosts",
        httpx.Response(200, json={"posts": [_post_view(i) for i in range(25)]}),
    )
    router.on(
        "app.bsky.feed.getPosts",
        httpx.Response(200, json={"posts": [_post_view(i) for i in range(25, 30)]}),
    )

    posts = await client.get_posts(
        [f"at://did:plc:author/app.bsky.feed.post/{i}" for i in range(30)]
    )

    assert len(router.called("app.bsky.feed.getPosts")) == 2
    assert all(c.url.host == "public.api.bsky.app" for c in router.calls)
    assert len(posts) == 30
    post = posts[7]
    assert (post.like_count, post.repost_count, post.reply_count) == (7, 14, 1)
    assert post.langs == ["pt"]
    assert post.author_handle == "autor.bsky.social"
    assert post.created_at is not None and post.created_at.year == 2026


async def test_get_profile_separates_self_labels(client: BlueskyClient, router: Router) -> None:
    router.on(
        "app.bsky.actor.getProfile",
        httpx.Response(200, json=json.loads((FIXTURES / "profile.json").read_text())),
    )

    account = await client.get_profile("robo.bsky.social")

    assert account.did == "did:plc:bot123"
    assert (account.followers_count, account.follows_count, account.posts_count) == (3, 900, 4200)
    assert account.self_labels == ["bot"]
    assert account.labels == ["bot", "spam"]
    assert account.avatar_url is None


async def test_get_author_feed_paginates_and_flags_reposts(
    client: BlueskyClient, router: Router
) -> None:
    repost = {
        "post": _post_view(99, did="did:plc:outro"),
        "reason": {
            "$type": "app.bsky.feed.defs#reasonRepost",
            "by": {"did": "did:plc:author", "handle": "a"},
            "indexedAt": "2026-09-16T10:00:00.000Z",
        },
    }
    router.on(
        "app.bsky.feed.getAuthorFeed",
        httpx.Response(200, json={"feed": [{"post": _post_view(1)}, repost], "cursor": "c1"}),
    )
    router.on(
        "app.bsky.feed.getAuthorFeed", httpx.Response(200, json={"feed": [{"post": _post_view(2)}]})
    )

    posts = await client.get_author_feed("autor.bsky.social", limit=10)

    assert [p.is_repost for p in posts] == [False, True, False]
    assert router.called("app.bsky.feed.getAuthorFeed")[1].url.params["cursor"] == "c1"


async def test_search_requires_login_and_persists_session(
    client: BlueskyClient, router: Router, settings: Settings
) -> None:
    router.on("com.atproto.server.createSession", _session_response())
    router.on("app.bsky.feed.searchPosts", httpx.Response(200, json={"posts": [_post_view(1)]}))

    posts = await client.search_posts("urna eletrônica", sort="top")

    assert len(posts) == 1
    search = router.called("app.bsky.feed.searchPosts")[0]
    assert search.url.host == "bsky.social"
    assert search.url.params["lang"] == "pt" and search.url.params["sort"] == "top"
    assert search.headers["authorization"].startswith("Bearer ")
    assert Path(settings.bluesky_session_path).exists()


async def test_stored_session_is_reused_without_create_session(
    settings: Settings, router: Router, client: BlueskyClient
) -> None:
    router.on("com.atproto.server.createSession", _session_response())
    router.on("app.bsky.feed.searchPosts", httpx.Response(200, json={"posts": []}))
    await client.search_posts("stf")
    assert len(router.called("createSession")) == 1

    second = BlueskyClient(
        settings,
        public_request=AsyncRequest(transport=httpx.MockTransport(router)),
        auth_request=AsyncRequest(transport=httpx.MockTransport(router)),
    )
    await second.search_posts("tse")

    assert len(router.called("createSession")) == 1  # reaproveitou a sessão do arquivo


async def test_login_without_credentials_fails_clearly(tmp_path: Path) -> None:
    client = BlueskyClient(Settings(bluesky_session_path=str(tmp_path / "none.session")))
    with pytest.raises(BlueskyAuthError):
        await client.login()


async def test_rate_limit_waits_until_reset_then_retries(
    client: BlueskyClient, router: Router, sleeps: list[float]
) -> None:
    reset = str(int(time.time()) + 5)
    router.on(
        "app.bsky.actor.getProfile",
        httpx.Response(
            429, headers={"ratelimit-reset": reset}, json={"error": "RateLimitExceeded"}
        ),
        httpx.Response(200, json=json.loads((FIXTURES / "profile.json").read_text())),
    )

    account = await client.get_profile("robo.bsky.social")

    assert account.handle == "robo.bsky.social"
    assert len(sleeps) == 1 and 1 <= sleeps[0] <= 6


async def test_ensure_bot_self_label_keeps_profile_fields(
    client: BlueskyClient, router: Router
) -> None:
    router.on("com.atproto.server.createSession", _session_response())
    router.on(
        "com.atproto.repo.getRecord",
        httpx.Response(
            200,
            json={
                "uri": "at://did:plc:contraria/app.bsky.actor.profile/self",
                "value": {
                    "$type": "app.bsky.actor.profile",
                    "displayName": "ContrarIA",
                    "description": "bot de checagem",
                },
            },
        ),
    )
    router.on(
        "com.atproto.repo.putRecord", httpx.Response(200, json={"uri": "at://x", "cid": "bafyx"})
    )

    changed = await client.ensure_bot_self_label()

    assert changed is True
    record = json.loads(router.called("com.atproto.repo.putRecord")[0].content)["record"]
    assert record["displayName"] == "ContrarIA"
    assert [v["val"] for v in record["labels"]["values"]] == ["bot"]
