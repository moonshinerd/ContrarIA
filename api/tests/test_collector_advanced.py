import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.jobs.collector import JetstreamConsumer, SearchPoller, _is_relevant


def test_is_relevant():
    # Palavras devem estar carregadas do YAML "politica.yaml"
    assert _is_relevant("Eleição no país") is True
    assert _is_relevant("urna eletrônica falhou") is True
    assert _is_relevant("não gosto de maçã") is False


@pytest.mark.asyncio
async def test_jetstream_consumer_message_parsing():
    repo = MagicMock()
    consumer = JetstreamConsumer(repo)

    msg_valid = '{"kind":"commit","commit":{"operation":"create","record":{"$type":"app.bsky.feed.post","langs":["pt"],"text":"urna eletronica","createdAt":"2024-01-01T12:00:00Z"},"cid":"c1","rkey":"r1"},"did":"did:1","time_us":100}'  # noqa: E501
    parsed = consumer.parse_message(msg_valid)
    assert parsed is not None
    assert parsed["uri"] == "at://did:1/app.bsky.feed.post/r1"
    assert parsed["text"] == "urna eletronica"

    # Invalid kind
    msg_invalid_kind = '{"kind":"delete"}'
    assert consumer.parse_message(msg_invalid_kind) is None

    # Missing pt lang
    msg_no_pt = '{"kind":"commit","commit":{"operation":"create","record":{"langs":["en"],"text":"urna eletronica"}}}'  # noqa: E501
    assert consumer.parse_message(msg_no_pt) is None

    # Irrelevant text
    msg_irrelevant = '{"kind":"commit","commit":{"operation":"create","record":{"$type":"app.bsky.feed.post","langs":["pt"],"text":"nada"}}}'  # noqa: E501
    assert consumer.parse_message(msg_irrelevant) is None


@pytest.mark.asyncio
async def test_search_poller_run_cycle(monkeypatch):
    repo = MagicMock()
    bsky_client = AsyncMock()

    class DummyPost:
        def __init__(self):
            self.uri = "p1"
            self.cid = "c1"
            self.author_did = "a1"
            self.text = "urna"
            self.langs = ["pt"]
            self.created_at = "2024-01-01T12:00:00Z"

    bsky_client.search_posts.return_value = [DummyPost()]

    poller = SearchPoller(repo, bsky_client, poll_interval_seconds=0)

    async def single_run():
        import datetime
        from datetime import UTC

        # This mocks the endless loop
        try:
            since = datetime.datetime.now(UTC) - datetime.timedelta(days=1)
            query = " OR ".join(["fake_kw"])
            posts = await poller.bsky_client.search_posts(
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
                poller.repo.upsert_posts(posts_data)
        except Exception:
            pass

    # Actually test the real logic inside the loop via overriding run or just letting it run one tick  # noqa: E501
    # But wait, SearchPoller.run is a while True loop with asyncio.sleep. We can patch sleep to raise an exception to exit loop  # noqa: E501
    async def mock_sleep(seconds):
        raise KeyboardInterrupt

    monkeypatch.setattr(asyncio, "sleep", mock_sleep)

    with pytest.raises(KeyboardInterrupt):
        await poller.run()

    repo.upsert_posts.assert_called_once()
    assert len(repo.upsert_posts.call_args[0][0]) == 1


@pytest.mark.asyncio
async def test_search_poller_error(monkeypatch):
    repo = MagicMock()
    bsky_client = AsyncMock()
    bsky_client.search_posts.side_effect = Exception("API error")

    poller = SearchPoller(repo, bsky_client, poll_interval_seconds=0)

    async def mock_sleep(seconds):
        raise KeyboardInterrupt

    monkeypatch.setattr(asyncio, "sleep", mock_sleep)

    with pytest.raises(KeyboardInterrupt):
        await poller.run()
    repo.upsert_posts.assert_not_called()


@pytest.mark.asyncio
async def test_jetstream_consumer_run(monkeypatch):
    import websockets

    repo = MagicMock()
    repo.get_cursor.return_value = 1000
    consumer = JetstreamConsumer(repo)

    class MockWS:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            pass

        async def recv(self):
            return '{"kind":"commit","commit":{"operation":"create","record":{"$type":"app.bsky.feed.post","langs":["pt"],"text":"urna eletronica","createdAt":"2024-01-01T12:00:00Z"},"cid":"c1","rkey":"r1"},"did":"did:1","time_us":100}'  # noqa: E501

    mock_connect = MagicMock(return_value=MockWS())
    monkeypatch.setattr(websockets, "connect", mock_connect)

    async def mock_sleep(seconds):
        raise KeyboardInterrupt

    monkeypatch.setattr(asyncio, "sleep", mock_sleep)

    # We patch consumer.parse_message to throw KeyboardInterrupt on second call to avoid infinite loop inside inner while  # noqa: E501
    call_count = 0
    original_parse = consumer.parse_message

    def fake_parse(msg):
        nonlocal call_count
        if call_count > 0:
            raise KeyboardInterrupt
        call_count += 1
        return original_parse(msg)

    monkeypatch.setattr(consumer, "parse_message", fake_parse)

    with pytest.raises(KeyboardInterrupt):
        await consumer.run()

    repo.upsert_posts.assert_called_once()
    repo.set_cursor.assert_called_once_with("jetstream", 100)


@pytest.mark.asyncio
async def test_search_poller_busca_uma_palavra_por_vez_e_deduplica():
    from datetime import UTC, datetime
    from types import SimpleNamespace

    from app.jobs.collector import POLITICAL_KEYWORDS

    def post(uri):
        return SimpleNamespace(
            uri=uri,
            cid="c",
            author_did="did:1",
            text="t",
            langs=["pt"],
            created_at=datetime.now(UTC),
        )

    repo = MagicMock()
    repo.existing_uris.return_value = set()
    bsky_client = MagicMock()
    queries: list[str] = []

    async def fake_search(query, **kwargs):
        queries.append(query)
        if query == "governo":
            raise RuntimeError("falha isolada")
        return [post("at://a"), post("at://b")]

    bsky_client.search_posts = fake_search
    total = await SearchPoller(repo, bsky_client).poll_once()

    # Sem "OR": o searchPosts do Bluesky o trata como termo obrigatório.
    assert all(" OR " not in q for q in queries)
    assert set(POLITICAL_KEYWORDS).issubset(queries)
    assert total == 2
    saved = repo.upsert_posts.call_args.args[0]
    assert {p["uri"] for p in saved} == {"at://a", "at://b"}


@pytest.mark.asyncio
async def test_search_poller_fila_cheia_admite_os_mais_populares_e_poda_o_resto():
    from datetime import UTC, datetime
    from types import SimpleNamespace

    from app.jobs.collector import IngestGate

    def post(uri, likes):
        return SimpleNamespace(
            uri=uri,
            cid="c",
            author_did="d",
            text="t",
            langs=["pt"],
            created_at=datetime.now(UTC),
            like_count=likes,
            repost_count=0,
            reply_count=0,
            quote_count=0,
        )

    repo = MagicMock()
    repo.pending_count.return_value = 100  # fila cheia
    repo.existing_uris.return_value = set()
    repo.trim_pending.return_value = 3
    bsky_client = MagicMock()

    async def fake_search(query, **kwargs):
        return [post("at://fraco", 1), post("at://viral", 50000), post("at://medio", 300)]

    bsky_client.search_posts = fake_search
    gate = IngestGate(repo, max_pending=2)
    assert await SearchPoller(repo, bsky_client, gate=gate).poll_once() == 2

    saved = repo.upsert_posts.call_args.args[0]
    # só os 2 mais populares (teto da fila), do mais para o menos popular, com prioridade gravada
    assert [p["uri"] for p in saved] == ["at://viral", "at://medio"]
    assert saved[0]["priority"] > saved[1]["priority"] > 0
    assert all(p["triage_status"] == "monitor" for p in saved)
    # a poda expira os menos badalados que já estavam na fila (ex.: posts do Jetstream sem nota)
    repo.trim_pending.assert_called_once_with(2)


def test_gate_invalidate_forca_nova_contagem():
    from app.jobs.collector import IngestGate

    repo = MagicMock()
    repo.pending_count.return_value = 100
    gate = IngestGate(repo, max_pending=100, refresh_seconds=3600)
    assert gate.room() == 0
    repo.pending_count.return_value = 40
    assert gate.room() == 0  # contagem em cache
    gate.invalidate()
    assert gate.room() == 60


@pytest.mark.asyncio
async def test_search_poller_ignora_posts_que_ja_existem_no_banco():
    from datetime import UTC, datetime
    from types import SimpleNamespace

    def post(uri):
        return SimpleNamespace(
            uri=uri, cid="c", author_did="d", text="t", langs=["pt"], created_at=datetime.now(UTC)
        )

    repo = MagicMock()
    repo.existing_uris.return_value = {"at://velho"}
    bsky_client = MagicMock()

    async def fake_search(query, **kwargs):
        return [post("at://velho"), post("at://novo")]

    bsky_client.search_posts = fake_search
    assert await SearchPoller(repo, bsky_client).poll_once() == 1
    assert [p["uri"] for p in repo.upsert_posts.call_args.args[0]] == ["at://novo"]


def test_claim_query_remove_rotulo_de_checagem_e_preserva_a_alegacao():
    from app.jobs.collector import _claim_query

    assert _claim_query({"title": "É falso que TSE anulou votos no Nordeste"}) == (
        "TSE anulou votos no Nordeste"
    )
    assert _claim_query({"title": "Checagem: boato"}) is None


@pytest.mark.asyncio
async def test_search_poller_prioriza_posts_encontrados_por_checagens(monkeypatch):
    from datetime import UTC, datetime
    from types import SimpleNamespace

    import app.jobs.collector as collector

    class FactArticles:
        def recent_for_collection(self, *, limit, max_age_days):
            assert (limit, max_age_days) == (2, 7)
            return [{"title": "É falso que urnas foram fraudadas", "summary": ""}]

    settings = SimpleNamespace(
        factcheck_search_enabled=True,
        factcheck_search_static_queries=["TSE manipulou"],
        factcheck_search_max_articles=2,
        factcheck_search_max_age_days=7,
        factcheck_search_max_queries=5,
        factcheck_search_priority_bonus=25.0,
    )
    monkeypatch.setattr(collector, "get_settings", lambda: settings)

    def post(uri, likes=0):
        return SimpleNamespace(
            uri=uri,
            cid="c",
            author_did="d",
            text="urna fraudada",
            langs=["pt"],
            created_at=datetime.now(UTC),
            like_count=likes,
            repost_count=0,
            reply_count=0,
            quote_count=0,
        )

    repo = MagicMock()
    repo.existing_uris.return_value = set()
    bsky_client = MagicMock()
    queries = []

    async def fake_search(query, **kwargs):
        queries.append(query)
        if query == "urnas foram fraudadas":
            return [post("at://guiado")]
        if query == "eleição":
            return [post("at://generico", likes=10_000)]
        return []

    bsky_client.search_posts = fake_search
    await SearchPoller(repo, bsky_client, fact_articles=FactArticles()).poll_once()

    assert queries[:2] == ["TSE manipulou", "urnas foram fraudadas"]
    saved = {item["uri"]: item for item in repo.upsert_posts.call_args.args[0]}
    assert saved["at://guiado"]["source"] == "factcheck_search"
    assert saved["at://guiado"]["priority"] >= 25
    assert saved["at://generico"]["source"] == "search"
    bsky_client.quote_post.assert_not_called()


@pytest.mark.asyncio
async def test_search_poller_reserva_vaga_para_busca_guiada_com_fila_cheia(monkeypatch):
    from datetime import UTC, datetime
    from types import SimpleNamespace

    import app.jobs.collector as collector

    settings = SimpleNamespace(
        factcheck_search_enabled=True,
        factcheck_search_static_queries=["urna fraudada"],
        factcheck_search_max_articles=0,
        factcheck_search_max_age_days=7,
        factcheck_search_max_queries=5,
        factcheck_search_priority_bonus=25.0,
        factcheck_search_reserve=1,
    )
    monkeypatch.setattr(collector, "get_settings", lambda: settings)

    def post(uri, likes):
        return SimpleNamespace(
            uri=uri,
            cid="c",
            author_did="d",
            text="texto",
            langs=["pt"],
            created_at=datetime.now(UTC),
            like_count=likes,
            repost_count=0,
            reply_count=0,
            quote_count=0,
        )

    repo = MagicMock()
    repo.existing_uris.return_value = set()
    bsky_client = MagicMock()

    async def fake_search(query, **kwargs):
        if query == "urna fraudada":
            return [post("at://guiado", 1)]
        if query == "eleição":
            return [post("at://viral", 100_000)]
        return []

    bsky_client.search_posts = fake_search
    gate = collector.IngestGate(repo, max_pending=1)
    await collector.SearchPoller(repo, bsky_client, gate=gate).poll_once()

    saved = repo.upsert_posts.call_args.args[0]
    assert len(saved) == 1
    assert saved[0]["uri"] == "at://guiado"
