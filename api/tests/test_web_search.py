import asyncio
import json

import httpx
import pytest

from app.clients.evidence.web_search import (
    DuckDuckGoClient,
    EvidenceSearchUnavailable,
    TavilyClient,
    WebSearchSource,
    parse_date,
)
from app.core.config import Settings


def settings(**kwargs):
    return Settings(_env_file=None, tavily_api_key="test-key", **kwargs)


def test_tavily_payload_mapping_and_concurrent_cache():
    requests = []

    def handler(request):
        requests.append(request)
        assert request.headers["Authorization"] == "Bearer test-key"
        assert json.loads(request.content) == {
            "query": "urna eletrônica",
            "topic": "news",
            "search_depth": "basic",
            "days": 7,
            "max_results": 5,
        }
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "url": "https://example.org/check",
                        "title": "Checagem",
                        "content": "Resumo",
                        "published_date": "Mon, 21 Sep 2026 10:00:00 GMT",
                    }
                ]
            },
        )

    source = TavilyClient(settings(), transport=httpx.MockTransport(handler))

    async def run():
        return await asyncio.gather(*[source.search(" urna   eletrônica ") for _ in range(5)])

    results = asyncio.run(run())
    assert len(requests) == 1
    assert results[0][0].source == "tavily"
    assert results[0][0].published_at.year == 2026


@pytest.mark.parametrize("status", [401, 429, 432, 433, 500])
def test_fallback_and_quota_cooldown(status):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status)

    config = settings()
    tavily = TavilyClient(config, transport=httpx.MockTransport(handler))
    ddg = DuckDuckGoClient(
        config,
        search_fn=lambda query, limit: [
            {"url": "https://example.org/fallback", "title": query, "body": "Evidência"}
        ],
    )
    source = WebSearchSource(config, tavily=tavily, duckduckgo=ddg)

    async def run():
        assert (await source.search("alegação 1"))[0].source == "duckduckgo"
        assert (await source.search("alegação 2"))[0].source == "duckduckgo"

    asyncio.run(run())
    assert len(calls) == (1 if status in (429, 432, 433) else 2)


def test_cache_expiry_and_capacity(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr("app.clients.evidence.web_search.monotonic", lambda: clock[0])
    calls = []
    source = DuckDuckGoClient(
        settings(web_cache_ttl_seconds=10, web_cache_max_entries=1),
        search_fn=lambda q, limit: calls.append(q) or [],
    )

    async def run():
        await source.search("a")
        await source.search("a")
        clock[0] = 11
        await source.search("a")
        await source.search("b")
        await source.search("a")

    asyncio.run(run())
    assert calls == ["a", "a", "b", "a"]
    assert len(source._cache) == 1


def test_sources_disabled_do_not_call_providers():
    def fail(*args):
        pytest.fail("Fonte desabilitada foi chamada")

    config = settings(tavily_enabled=False, duckduckgo_enabled=False)
    source = WebSearchSource(
        config,
        tavily=TavilyClient(config, transport=httpx.MockTransport(fail)),
        duckduckgo=DuckDuckGoClient(config, search_fn=fail),
    )
    assert asyncio.run(source.search("alegação")) == []


def test_missing_key_and_invalid_dates():
    config = Settings(_env_file=None, tavily_api_key="")
    ddg = DuckDuckGoClient(config, search_fn=lambda q, n: [{"url": "https://example.org"}])
    assert (
        asyncio.run(WebSearchSource(config, duckduckgo=ddg).search("x"))[0].source == "duckduckgo"
    )
    assert parse_date("inválida") is None
    assert parse_date("2026-09-21").tzinfo is not None


def test_timeout_falls_back_without_caching_failure():
    calls = []

    def handler(request):
        calls.append(request)
        raise httpx.ReadTimeout("timeout", request=request)

    config = settings()
    ddg = DuckDuckGoClient(config, search_fn=lambda q, n: [{"url": "https://example.org"}])
    tavily = TavilyClient(config, transport=httpx.MockTransport(handler))
    source = WebSearchSource(config, tavily=tavily, duckduckgo=ddg)
    assert asyncio.run(source.search("notícia"))[0].source == "duckduckgo"
    assert len(tavily._cache) == 0


def test_ddgs_region_and_backend(monkeypatch):
    class FakeDDGS:
        def __init__(self, *, timeout):
            assert timeout == 20

        def news(self, query, **kwargs):
            assert query == "notícia"
            assert kwargs == {"region": "br-pt", "max_results": 3, "backend": "duckduckgo"}
            return []

        text = news

    monkeypatch.setattr("ddgs.DDGS", FakeDDGS)
    assert asyncio.run(DuckDuckGoClient(settings()).search("notícia", limit=3)) == []


@pytest.mark.parametrize("news_empty_exception", [False, True])
def test_news_empty_falls_back_to_text_and_caches(monkeypatch, news_empty_exception):
    from ddgs.exceptions import DDGSException

    calls = []

    class FakeDDGS:
        def __init__(self, **kwargs):
            pass

        def news(self, query, **kwargs):
            calls.append("news")
            if news_empty_exception:
                raise DDGSException("No results found.")
            return []

        def text(self, query, **kwargs):
            calls.append("text")
            assert query == "alegação completa"
            assert kwargs["region"] == "br-pt"
            assert kwargs["backend"] == "duckduckgo"
            return [{"href": "https://example.org/check", "title": "Checagem", "body": "Resumo"}]

    monkeypatch.setattr("ddgs.DDGS", FakeDDGS)
    source = DuckDuckGoClient(settings())

    async def run():
        first = await source.search("alegação completa")
        assert first[0].url == "https://example.org/check"
        assert first[0].published_at is None
        assert await source.search("alegação completa") == first

    asyncio.run(run())
    assert calls == ["news", "text"]


def test_empty_web_is_not_logged_as_unavailable(monkeypatch, caplog):
    from ddgs.exceptions import DDGSException

    class FakeDDGS:
        def __init__(self, **kwargs):
            pass

        def news(self, *args, **kwargs):
            raise DDGSException("No results found.")

        text = news

    monkeypatch.setattr("ddgs.DDGS", FakeDDGS)
    source = WebSearchSource(settings(tavily_enabled=False), raise_on_failure=True)
    assert asyncio.run(source.search("sem correspondência")) == []
    assert "indisponível" not in caplog.text


def test_news_results_do_not_trigger_general_search(monkeypatch):
    class FakeDDGS:
        def __init__(self, **kwargs):
            pass

        def news(self, *args, **kwargs):
            return [{"url": "https://example.org/news"}]

        def text(self, *args, **kwargs):
            pytest.fail("Notícias já forneceram resultados")

    monkeypatch.setattr("ddgs.DDGS", FakeDDGS)
    assert asyncio.run(DuckDuckGoClient(settings()).search("notícia"))[0].url.endswith("news")


@pytest.mark.parametrize("error_type", ["TimeoutException", "RatelimitException", "DDGSException"])
def test_real_provider_errors_are_not_cached_as_empty(monkeypatch, error_type):
    from ddgs import exceptions

    class FakeDDGS:
        def __init__(self, **kwargs):
            pass

        def news(self, *args, **kwargs):
            raise getattr(exceptions, error_type)("provider failed")

        text = news

    monkeypatch.setattr("ddgs.DDGS", FakeDDGS)
    config = settings(tavily_enabled=False)
    ddg = DuckDuckGoClient(config)
    source = WebSearchSource(config, duckduckgo=ddg, raise_on_failure=True)
    with pytest.raises(EvidenceSearchUnavailable):
        asyncio.run(source.search("teste"))
    assert not ddg._cache


def test_web_search_fallback_from_tavily_missing_key_to_ddg_general(monkeypatch, caplog):
    from ddgs.exceptions import DDGSException

    calls = []

    class FakeDDGS:
        def __init__(self, **kwargs):
            pass

        def news(self, query, **kwargs):
            calls.append("news")
            raise DDGSException("No results found.")

        def text(self, query, **kwargs):
            calls.append("text")
            return [{"href": "https://example.org/tse-papa", "title": "TSE Papa", "body": "Falso"}]

    monkeypatch.setattr("ddgs.DDGS", FakeDDGS)
    config = Settings(_env_file=None, tavily_api_key="", duckduckgo_enabled=True)
    source = WebSearchSource(config)

    results = asyncio.run(source.search("TSE eleição papa urnas eletrônicas"))
    assert calls == ["news", "text"]
    assert len(results) == 1
    assert results[0].url == "https://example.org/tse-papa"
    assert results[0].source == "duckduckgo"
    assert "indisponível" not in caplog.text


def test_no_results_anywhere_is_not_treated_as_failure_even_with_raise_on_failure(
    monkeypatch, caplog
):
    from ddgs.exceptions import DDGSException

    class FakeDDGS:
        def __init__(self, **kwargs):
            pass

        def news(self, *args, **kwargs):
            raise DDGSException("No results found.")

        text = news

    monkeypatch.setattr("ddgs.DDGS", FakeDDGS)
    config = Settings(_env_file=None, tavily_api_key="", duckduckgo_enabled=True)
    source = WebSearchSource(config, raise_on_failure=True)

    results = asyncio.run(source.search("TSE eleição papa urnas eletrônicas"))
    assert results == []
    assert "indisponível" not in caplog.text
