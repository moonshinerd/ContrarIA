import asyncio

import httpx
import pytest

from app.clients.evidence.web_search import (
    DuckDuckGoClient,
    EvidenceSearchUnavailable,
    SearXNGClient,
    WebSearchSource,
    parse_date,
)
from app.core.config import Settings


def settings(**kwargs):
    kwargs.setdefault("searxng_enabled", False)
    return Settings(_env_file=None, **kwargs)


@pytest.mark.parametrize("status", [401, 429, 500])
def test_searxng_failure_falls_back_to_duckduckgo(status):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status)

    config = settings(searxng_enabled=True, searxng_base_url="http://mock-searxng:8080")
    searxng = SearXNGClient(config, transport=httpx.MockTransport(handler))
    ddg = DuckDuckGoClient(
        config,
        search_fn=lambda query, limit: [
            {"url": "https://example.org/fallback", "title": query, "body": "Evidência"}
        ],
    )
    source = WebSearchSource(config, searxng=searxng, duckduckgo=ddg)

    async def run():
        assert (await source.search("alegação 1"))[0].source == "duckduckgo"
        assert (await source.search("alegação 2"))[0].source == "duckduckgo"

    asyncio.run(run())
    assert len(calls) >= 1


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

    config = settings(searxng_enabled=False, duckduckgo_enabled=False)
    source = WebSearchSource(
        config,
        searxng=SearXNGClient(config, transport=httpx.MockTransport(fail)),
        duckduckgo=DuckDuckGoClient(config, search_fn=fail),
    )
    assert asyncio.run(source.search("alegação")) == []


def test_missing_key_and_invalid_dates():
    config = Settings(_env_file=None, searxng_enabled=False)
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

    config = settings(searxng_enabled=True, searxng_base_url="http://mock-searxng:8080")
    ddg = DuckDuckGoClient(config, search_fn=lambda q, n: [{"url": "https://example.org"}])
    searxng = SearXNGClient(config, transport=httpx.MockTransport(handler))
    source = WebSearchSource(config, searxng=searxng, duckduckgo=ddg)
    assert asyncio.run(source.search("notícia"))[0].source == "duckduckgo"
    assert len(searxng._cache) == 0


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
    source = WebSearchSource(settings(), raise_on_failure=True)
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
    config = settings()
    ddg = DuckDuckGoClient(config)
    source = WebSearchSource(config, duckduckgo=ddg, raise_on_failure=True)
    with pytest.raises(EvidenceSearchUnavailable):
        asyncio.run(source.search("teste"))
    assert not ddg._cache


def test_web_search_falls_back_to_ddg_general_when_news_is_empty(monkeypatch, caplog):
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
    config = settings(duckduckgo_enabled=True)
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
    config = settings(duckduckgo_enabled=True)
    source = WebSearchSource(config, raise_on_failure=True)

    results = asyncio.run(source.search("TSE eleição papa urnas eletrônicas"))
    assert results == []
    assert "indisponível" not in caplog.text


def test_searxng_payload_mapping_and_concurrent_cache():
    requests = []

    def handler(request: httpx.Request):
        requests.append(request)
        assert request.url.params["q"] == "Ana Clara Flávio Bolsonaro"
        assert request.url.params["format"] == "json"
        assert request.url.params["language"] == "pt-BR"
        assert request.url.params["categories"] == "news,general"
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "url": "https://atarde.com.br/politica/materia-teste",
                        "title": "A Tarde Teste",
                        "content": "Conteúdo factual da matéria",
                        "publishedDate": "2026-09-30T10:00:00Z",
                    },
                    {
                        "url": "https://twitter.com/post/12345",
                        "title": "Post do Twitter",
                        "content": "Deve ser filtrado por is_valid_evidence_url",
                    },
                ]
            },
        )

    config = settings(
        searxng_enabled=True,
        searxng_base_url="http://mock-searxng:8080",
        searxng_categories="news,general",
    )
    source = SearXNGClient(config, transport=httpx.MockTransport(handler))

    async def run():
        return await asyncio.gather(
            *[source.search(" Ana Clara  Flávio Bolsonaro ") for _ in range(3)]
        )

    results = asyncio.run(run())
    assert len(requests) == 1  # Cache funcionou para chamadas simultâneas
    assert len(results[0]) == 1  # Twitter filtrado
    evidence = results[0][0]
    assert evidence.source == "searxng"
    assert evidence.url == "https://atarde.com.br/politica/materia-teste"
    assert evidence.title == "A Tarde Teste"
    assert evidence.snippet == "Conteúdo factual da matéria"
    assert evidence.published_at.year == 2026


def test_fonte_com_falha_entra_em_espera_e_responde_vazio_na_hora(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr("app.clients.evidence.web_search.monotonic", lambda: clock[0])
    calls = []

    def boom(query, limit):
        calls.append(query)
        raise RuntimeError("fora do ar")

    config = settings(duckduckgo_enabled=True, evidence_failure_cooldown_seconds=30)
    source = DuckDuckGoClient(config, search_fn=boom)

    async def run():
        with pytest.raises(RuntimeError):
            await source.search("a")
        assert await source.search("b") == []  # em espera: nem chama o provedor
        assert calls == ["a"]
        clock[0] = 31  # passou a espera de 30 s
        with pytest.raises(RuntimeError):
            await source.search("c")
        assert source._unavailable_until == 31 + 60  # a espera dobrou

    asyncio.run(run())


def test_fonte_lenta_nao_segura_as_outras_consultas():
    """Sem lock global: uma consulta travada não deixa as demais na fila."""
    finished = []

    async def run():
        release = asyncio.Event()

        class Slow(DuckDuckGoClient):
            async def _search(self, query, limit):
                if query == "lenta":
                    await release.wait()
                finished.append(query)
                return []

        source = Slow(settings(duckduckgo_enabled=True))
        slow = asyncio.create_task(source.search("lenta"))
        await asyncio.sleep(0)
        await asyncio.wait_for(source.search("rapida"), timeout=1)
        assert finished == ["rapida"]
        release.set()
        await slow

    asyncio.run(run())


def test_provedor_que_estoura_o_prazo_cede_a_vez_e_entra_em_espera():
    config = settings(
        searxng_enabled=True,
        searxng_base_url="http://mock",
        evidence_provider_timeout_seconds=0.05,
    )

    class Hung(SearXNGClient):
        async def _search(self, query, limit):
            await asyncio.sleep(5)

    ddg = DuckDuckGoClient(
        config, search_fn=lambda q, n: [{"url": "https://example.org/ok", "title": "t"}]
    )
    hung = Hung(config)
    source = WebSearchSource(config, searxng=hung, duckduckgo=ddg)

    async def run():
        results = await asyncio.wait_for(source.search("alegação"), timeout=2)
        assert results[0].source == "duckduckgo"
        assert hung._unavailable_until > 0  # o disjuntor abriu

    asyncio.run(run())
