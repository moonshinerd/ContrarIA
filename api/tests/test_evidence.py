import json
from pathlib import Path

import httpx
import pytest

from app.clients.evidence import EVIDENCE_SOURCES, get_evidence_source
from app.clients.evidence.google_factcheck import GoogleFactCheckClient
from app.clients.evidence.wikipedia import WikipediaClient

# Caminho para as fixtures salvas
FIXTURES_DIR = Path(__file__).parent / "fixtures" / "evidence"


@pytest.fixture
def wikipedia_fixture():
    with open(FIXTURES_DIR / "wikipedia_search.json", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def factcheck_fixture():
    with open(FIXTURES_DIR / "google_factcheck_search.json", encoding="utf-8") as f:
        return json.load(f)


def test_registry_evidence_sources():
    """Valida se as fontes estão registradas e instanciáveis pelo nome."""
    assert "wikipedia" in EVIDENCE_SOURCES
    assert "google_factcheck" in EVIDENCE_SOURCES

    wiki = get_evidence_source("wikipedia")
    assert isinstance(wiki, WikipediaClient)
    assert wiki.name == "wikipedia"

    fact = get_evidence_source("google_factcheck", api_key="fake-key")
    assert isinstance(fact, GoogleFactCheckClient)
    assert fact.name == "google_factcheck"


@pytest.mark.anyio
async def test_wikipedia_search_with_fixture(wikipedia_fixture, monkeypatch):
    """Testa a busca da Wikipédia usando fixture gravada."""

    async def mock_get(self, url, *args, **kwargs):
        if "summary" in str(url):
            return httpx.Response(
                200,
                json={
                    "extract": "A urna eletrônica brasileira é um sistema seguro...",
                    "content_urls": {"desktop": {"page": "https://pt.wikipedia.org/wiki/Urna"}},
                },
                request=httpx.Request("GET", str(url)),
            )
        return httpx.Response(
            200,
            json=wikipedia_fixture,
            request=httpx.Request("GET", str(url)),
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    client = WikipediaClient()
    evidences = await client.search("urna eletrônica", limit=1)

    assert len(evidences) == 1
    ev = evidences[0]
    assert ev.source == "wikipedia"
    assert "Urna eletrônica" in ev.title
    assert len(ev.snippet) > 0
    assert ev.rating is None


@pytest.mark.anyio
async def test_google_factcheck_search_with_fixture(factcheck_fixture, monkeypatch):
    """Testa o critério da issue: consulta devolve ao menos uma ClaimReview em PT."""

    async def mock_get(self, url, *args, **kwargs):
        return httpx.Response(
            200,
            json=factcheck_fixture,
            request=httpx.Request("GET", str(url)),
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    client = GoogleFactCheckClient(api_key="fake-test-key")
    evidences = await client.search("urna eletrônica fraude", limit=5)

    assert len(evidences) >= 1
    ev = evidences[0]
    assert ev.source == "google_factcheck"
    assert "aosfatos.org" in ev.url
    assert ev.rating == "Falso"
    assert "Checagem por Aos Fatos" in ev.snippet
    assert ev.published_at is not None


@pytest.mark.anyio
async def test_evidence_cache_prevents_duplicate_calls(factcheck_fixture, monkeypatch):
    """Garante que chamadas repetidas usam o cache e poupam cota."""
    call_count = 0

    async def mock_get(self, url, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, json=factcheck_fixture, request=httpx.Request("GET", str(url)))

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    client = GoogleFactCheckClient(api_key="fake-key")

    # Primeira busca: faz a requisição HTTP
    primeira = await client.search("urna eletrônica fraude", limit=5)
    assert call_count == 1

    # Segunda busca idêntica: deve vir do cache sem disparar HTTP
    segunda = await client.search("urna eletrônica fraude", limit=5)
    assert call_count == 1
    assert primeira == segunda
