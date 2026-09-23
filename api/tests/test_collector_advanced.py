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

    msg_valid = '{"kind":"commit","commit":{"operation":"create","record":{"$type":"app.bsky.feed.post","langs":["pt"],"text":"urna eletronica","createdAt":"2024-01-01T12:00:00Z"},"cid":"c1","rkey":"r1"},"did":"did:1","time_us":100}'
    parsed = consumer.parse_message(msg_valid)
    assert parsed is not None
    assert parsed["uri"] == "at://did:1/app.bsky.feed.post/r1"
    assert parsed["text"] == "urna eletronica"

    # Invalid kind
    msg_invalid_kind = '{"kind":"delete"}'
    assert consumer.parse_message(msg_invalid_kind) is None

    # Missing pt lang
    msg_no_pt = (
        '{"kind":"commit","commit":{"operation":"create","record":{"langs":["en"],"text":"urna eletronica"}}}'
    )
    assert consumer.parse_message(msg_no_pt) is None

    # Irrelevant text
    msg_irrelevant = (
        '{"kind":"commit","commit":{"operation":"create","record":{"$type":"app.bsky.feed.post","langs":["pt"],"text":"nada"}}}'
    )
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

    # Actually test the real logic inside the loop via overriding run or just letting it run one tick
    # But wait, SearchPoller.run is a while True loop with asyncio.sleep. We can patch sleep to raise an exception to exit loop
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
            return '{"kind":"commit","commit":{"operation":"create","record":{"$type":"app.bsky.feed.post","langs":["pt"],"text":"urna eletronica","createdAt":"2024-01-01T12:00:00Z"},"cid":"c1","rkey":"r1"},"did":"did:1","time_us":100}'

    mock_connect = MagicMock(return_value=MockWS())
    monkeypatch.setattr(websockets, "connect", mock_connect)

    async def mock_sleep(seconds):
        raise KeyboardInterrupt

    monkeypatch.setattr(asyncio, "sleep", mock_sleep)

    # We patch consumer.parse_message to throw KeyboardInterrupt on second call to avoid infinite loop inside inner while
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
