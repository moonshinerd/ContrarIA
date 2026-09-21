import json
import logging
import time
from pathlib import Path

import httpx
import pytest

from app.clients.evidence import EVIDENCE_SOURCES, get_evidence_source
from app.clients.evidence.cache import TTLCache
from app.clients.evidence.google_factcheck import GoogleFactCheckClient
from app.clients.evidence.ratelimit import RateLimiter
from app.clients.evidence.wikipedia import WikipediaClient

FIXTURES = Path(__file__).parent / "fixtures" / "evidence"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class Recorder:
    """Transporte falso que responde por handler e guarda as requisições."""

    def __init__(self, handler):
        self.requests: list[httpx.Request] = []
        self.transport = httpx.MockTransport(self._handle)
        self._handler = handler

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self._handler(request)


def google(recorder: Recorder, **kwargs) -> GoogleFactCheckClient:
    return GoogleFactCheckClient(api_key="chave-de-teste", transport=recorder.transport, **kwargs)


def wikipedia_handler(summary_status: int = 200):
    def handler(request: httpx.Request) -> httpx.Response:
        if "/page/summary/" in request.url.path:
            if summary_status != 200:
                return httpx.Response(summary_status)
            return httpx.Response(200, json=load("wikipedia_summary.json"))
        return httpx.Response(200, json=load("wikipedia_search.json"))

    return handler


def test_registry_evidence_sources():
    assert {"wikipedia", "google_factcheck"} <= set(EVIDENCE_SOURCES)

    wiki = get_evidence_source("wikipedia")
    assert isinstance(wiki, WikipediaClient)
    fact = get_evidence_source("google_factcheck", api_key="chave-de-teste")
    assert isinstance(fact, GoogleFactCheckClient)

    with pytest.raises(ValueError, match="desconhecida"):
        get_evidence_source("inexistente")


async def test_google_factcheck_returns_portuguese_claim_reviews():
    """Critério de pronto da issue #20: 'urna eletrônica fraude' devolve ClaimReview em PT."""
    rec = Recorder(lambda request: httpx.Response(200, json=load("google_factcheck_search.json")))

    evidences = await google(rec).search("urna eletrônica fraude", limit=5)

    assert len(evidences) >= 1
    first = evidences[0]
    assert first.source == "google_factcheck"
    assert first.url.startswith("https://")
    assert first.rating
    assert first.snippet.startswith("Checagem por ")
    assert first.published_at is not None
    params = rec.requests[0].url.params
    assert params["languageCode"] == "pt"
    assert params["query"] == "urna eletrônica fraude"
    assert "maxAgeDays" not in params


async def test_google_factcheck_respects_limit_and_max_age_days():
    rec = Recorder(lambda request: httpx.Response(200, json=load("google_factcheck_search.json")))

    evidences = await google(rec, max_age_days=30).search("urna", limit=2)

    assert len(evidences) == 2
    assert rec.requests[0].url.params["maxAgeDays"] == "30"
    assert rec.requests[0].url.params["pageSize"] == "2"


async def test_google_factcheck_without_key_warns_and_skips_http(caplog):
    rec = Recorder(lambda request: httpx.Response(200, json={}))
    client = GoogleFactCheckClient(api_key="", transport=rec.transport)

    with caplog.at_level(logging.WARNING):
        assert await client.search("urna") == []

    assert rec.requests == []
    assert "GOOGLE_FACTCHECK_API_KEY" in caplog.text


@pytest.mark.parametrize("status", [400, 403, 429, 500])
async def test_google_factcheck_http_error_logs_status_without_leaking_key(status, caplog):
    rec = Recorder(lambda request: httpx.Response(status, json={"error": {}}))

    with caplog.at_level(logging.WARNING):
        assert await google(rec).search("urna") == []

    assert f"HTTP {status}" in caplog.text
    assert "chave-de-teste" not in caplog.text


async def test_google_factcheck_network_error_returns_empty(caplog):
    def handler(request):
        raise httpx.ConnectError("sem rede", request=request)

    with caplog.at_level(logging.WARNING):
        assert await google(Recorder(handler)).search("urna") == []

    assert "ConnectError" in caplog.text


async def test_google_factcheck_empty_response_is_not_an_error():
    rec = Recorder(lambda request: httpx.Response(200, json={}))
    assert await google(rec).search("assunto sem checagem") == []


async def test_evidence_cache_prevents_duplicate_calls():
    rec = Recorder(lambda request: httpx.Response(200, json=load("google_factcheck_search.json")))
    client = google(rec)

    primeira = await client.search("urna eletrônica fraude", limit=5)
    segunda = await client.search("urna eletrônica fraude", limit=5)

    assert len(rec.requests) == 1
    assert primeira == segunda

    await client.search("outra consulta", limit=5)
    assert len(rec.requests) == 2


async def test_cached_result_is_isolated_from_caller_mutation():
    rec = Recorder(lambda request: httpx.Response(200, json=load("google_factcheck_search.json")))
    client = google(rec)

    primeira = await client.search("urna", limit=5)
    primeira.clear()

    assert len(await client.search("urna", limit=5)) > 0


async def test_failures_are_not_cached():
    calls = iter(
        [httpx.Response(500), httpx.Response(200, json=load("google_factcheck_search.json"))]
    )
    rec = Recorder(lambda request: next(calls))
    client = google(rec)

    assert await client.search("urna") == []
    assert len(await client.search("urna")) > 0


def test_ttl_cache_expires_entries(monkeypatch):
    cache = TTLCache(ttl_seconds=10)
    now = time.monotonic()
    monkeypatch.setattr(time, "monotonic", lambda: now)
    cache.set("k", [1])
    assert cache.get("k") == [1]

    monkeypatch.setattr(time, "monotonic", lambda: now + 11)
    assert cache.get("k") is None


async def test_wikipedia_search_uses_summary_and_identifiable_user_agent():
    rec = Recorder(wikipedia_handler())

    evidences = await WikipediaClient(transport=rec.transport).search("urna eletrônica fraude")

    assert len(evidences) == 2
    first = evidences[0]
    assert first.source == "wikipedia"
    assert first.title == "Urna eletrônica (Brasil)"
    assert first.url == "https://pt.wikipedia.org/wiki/Urna_eletr%C3%B4nica_(Brasil)"
    assert first.snippet.startswith("No Brasil, a urna eletrônica")
    assert first.rating is None
    search, *summaries = rec.requests
    assert search.url.params["srsearch"] == "urna eletrônica fraude"
    assert len(summaries) == 2
    assert all("ContrarIABot" in r.headers["user-agent"] for r in rec.requests)


async def test_wikipedia_summary_url_is_percent_encoded():
    rec = Recorder(wikipedia_handler())

    await WikipediaClient(transport=rec.transport).search("urna", limit=1)

    assert rec.requests[1].url.raw_path.decode() == (
        "/api/rest_v1/page/summary/Urna_eletr%C3%B4nica_%28Brasil%29"
    )


async def test_wikipedia_falls_back_to_clean_search_snippet_when_summary_fails():
    rec = Recorder(wikipedia_handler(summary_status=404))

    evidences = await WikipediaClient(transport=rec.transport).search("urna")

    snippet = evidences[0].snippet
    assert snippet
    assert "<span" not in snippet and "&quot;" not in snippet
    assert evidences[0].url.startswith("https://pt.wikipedia.org/wiki/")


async def test_wikipedia_search_failure_logs_and_returns_empty(caplog):
    rec = Recorder(lambda request: httpx.Response(503))

    with caplog.at_level(logging.WARNING):
        assert await WikipediaClient(transport=rec.transport).search("urna") == []

    assert "HTTP 503" in caplog.text


async def test_google_factcheck_429_opens_cooldown_and_honors_retry_after(caplog):
    calls = iter([httpx.Response(429, headers={"Retry-After": "30"})])
    rec = Recorder(lambda request: next(calls))
    client = google(rec)

    with caplog.at_level(logging.WARNING):
        assert await client.search("urna") == []
        assert await client.search("outra consulta") == []

    assert len(rec.requests) == 1  # a segunda nem chegou a sair
    assert "em pausa" in caplog.text
    assert 25 < client._blocked_until - time.monotonic() <= 30


async def test_google_factcheck_resumes_after_cooldown(monkeypatch):
    calls = iter(
        [httpx.Response(429), httpx.Response(200, json=load("google_factcheck_search.json"))]
    )
    rec = Recorder(lambda request: next(calls))
    client = google(rec)

    assert await client.search("urna") == []
    client._blocked_until = 0.0  # pausa vencida

    assert len(await client.search("urna")) > 0


async def test_rate_limiter_delays_calls_over_the_limit():
    now = 0.0
    waited: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        nonlocal now
        waited.append(seconds)
        now += seconds

    limiter = RateLimiter(2, period=60.0, clock=lambda: now, sleep=fake_sleep)
    for _ in range(3):
        await limiter.acquire()

    assert waited == [60.0]  # a 3ª chamada esperou a janela abrir


async def test_google_factcheck_uses_rate_limiter_per_request():
    rec = Recorder(lambda request: httpx.Response(200, json={}))
    acquired = 0

    class Counting(RateLimiter):
        async def acquire(self) -> None:
            nonlocal acquired
            acquired += 1

    client = google(rec, rate_limiter=Counting(10))
    await client.search("a")
    await client.search("b")
    await client.search("a")  # vem do cache: não gasta cota

    assert acquired == 2


async def test_cache_key_ignores_case_and_spacing():
    rec = Recorder(lambda request: httpx.Response(200, json=load("google_factcheck_search.json")))
    client = google(rec)

    await client.search("Urna  Eletrônica")
    await client.search("urna eletrônica ")

    assert len(rec.requests) == 1


def test_ttl_cache_evicts_oldest_beyond_max_entries():
    cache = TTLCache(ttl_seconds=60, max_entries=2)
    for key in ("a", "b", "c"):
        cache.set(key, key)

    assert len(cache) == 2
    assert cache.get("a") is None
    assert cache.get("c") == "c"


async def test_wikipedia_limits_concurrent_summary_requests():
    import asyncio

    active = peak = 0
    search = load("wikipedia_search.json")
    search["query"]["search"] = search["query"]["search"] * 4  # 8 resultados

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal active, peak
        if "/page/summary/" not in request.url.path:
            return httpx.Response(200, json=search)
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.01)
        active -= 1
        return httpx.Response(200, json=load("wikipedia_summary.json"))

    client = WikipediaClient(transport=httpx.MockTransport(handler), max_concurrency=3)
    evidences = await client.search("urna", limit=8)

    assert len(evidences) == 8
    assert peak <= 3
