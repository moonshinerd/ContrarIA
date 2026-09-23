from unittest.mock import AsyncMock, MagicMock

import pytest

from app.clients.bluesky_client import BlueskyClient


@pytest.fixture
def bsky():
    settings = MagicMock()
    settings.bluesky_handle = "bot"
    settings.bluesky_app_password = "pw"
    client = BlueskyClient(settings)
    client._public = AsyncMock()
    client._auth = AsyncMock()
    client._auth._session = MagicMock(did="did:bot")
    client._logged_in = True
    return client


@pytest.mark.asyncio
async def test_quote_post(bsky, monkeypatch):
    # Mock atproto TextBuilder
    bsky._auth.send_post.return_value = MagicMock(uri="at://new_post")

    # We patch _authenticated to just run the fn
    async def mock_auth(fn):
        return await fn()

    monkeypatch.setattr(bsky, "_authenticated", mock_auth)

    uri = await bsky.quote_post("at://target", "cid_target", "Hello", "http://fonte.com")
    assert uri == "at://new_post"
    bsky._auth.send_post.assert_called_once()


@pytest.mark.asyncio
async def test_has_postgate_quote_disabled(bsky, monkeypatch):
    async def mock_call(fn):
        return await fn()

    monkeypatch.setattr(bsky, "_call", mock_call)

    # Mocking disabled rule
    record_mock = MagicMock()
    record_mock.value = MagicMock()

    import atproto

    def mock_get_model_as_dict(val):
        return {"embeddingRules": [{"$type": "app.bsky.feed.postgate#disableRule"}]}

    monkeypatch.setattr(atproto.models, "get_model_as_dict", mock_get_model_as_dict)

    bsky._public.com.atproto.repo.get_record.return_value = record_mock

    res = await bsky.has_postgate_quote_disabled("at://did:1/app.bsky.feed.post/r1")
    assert res is True

    # No rule
    def mock_get_model_as_dict_empty(val):
        return {"embeddingRules": []}

    monkeypatch.setattr(atproto.models, "get_model_as_dict", mock_get_model_as_dict_empty)
    res2 = await bsky.has_postgate_quote_disabled("at://did:1/app.bsky.feed.post/r1")
    assert res2 is False

    # Exception
    bsky._public.com.atproto.repo.get_record.side_effect = Exception("error")
    res3 = await bsky.has_postgate_quote_disabled("at://did:1/app.bsky.feed.post/r1")
    # Em falha de leitura do postgate, bloquear quote é a escolha segura.
    assert res3 is True

    # Invalid URI
    assert await bsky.has_postgate_quote_disabled("invalid_uri") is False
