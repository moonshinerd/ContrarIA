from datetime import UTC, datetime

import pytest

from app.core.config import Settings
from app.domain.entities import Evidence, Post, VerdictLabel
from app.jobs.claim_harvester import ClaimHarvester


class FakeFactCheck:
    def __init__(self, evidences):
        self.evidences = evidences

    async def search(self, query, *, limit=5):
        return list(self.evidences)


class FakeBluesky:
    def __init__(self, posts):
        self.posts = posts
        self.queries: list[str] = []

    async def search_posts(self, *, query, **_):
        self.queries.append(query)
        return list(self.posts)


class FakeRepo:
    def __init__(self):
        self.upserts: list[dict] = []

    def recent_texts(self, limit):
        return ["Lula hoje", "Lula e Flávio", "eleição Lula", "Gilmar no STF"]

    def upsert_posts(self, rows):
        self.upserts.extend(rows)
        return len(rows)


class FakePipeline:
    def __init__(self):
        self.calls = []

    async def analyze(self, post, *, verdict=None):
        self.calls.append((post, verdict))


def _post(uri, text):
    return Post(uri=uri, cid="c", author_did="did:a", text=text, created_at=datetime.now(UTC))


CHECK = Evidence(
    source="google_factcheck",
    url="https://www.aosfatos.org/noticias/gilmar-celular/",
    title="Gilmar não votou usando celular",
    snippet="Checagem por Aos Fatos: Gilmar Mendes vota com celular na cabine",
    rating="falso",
)


def _harvester(posts, evidences=(CHECK,)):
    settings = Settings(_env_file=None, claim_harvest_queries=["Gilmar"])
    pipeline = FakePipeline()
    repo = FakeRepo()
    bluesky = FakeBluesky(posts)
    harvester = ClaimHarvester(
        settings, bluesky, repo, pipeline, factcheck=FakeFactCheck(list(evidences))
    )
    return harvester, bluesky, repo, pipeline


@pytest.mark.anyio
async def test_harvest_keeps_posts_that_repeat_the_claim_and_drops_debunks():
    spreads = _post("at://1", "Gilmar Mendes vota em MT usando celular em cabine, absurdo")
    debunk = _post("at://2", "É falso que Gilmar Mendes vota com celular na cabine")
    unrelated = _post("at://3", "Hoje tem jogo do Flamengo, alguém vai?")
    harvester, bluesky, _, _ = _harvester([spreads, debunk, unrelated])

    report = await harvester.run()

    assert report["new_candidates"] == 1
    assert [c.post.uri for c in harvester.backlog] == ["at://1"]
    # Termos raros da alegação, não o nome mais comum do corpus.
    assert "cabine" in bluesky.queries[0] or "celular" in bluesky.queries[0]


@pytest.mark.anyio
async def test_release_one_sends_a_false_verdict_with_the_check_as_source():
    harvester, _, repo, pipeline = _harvester(
        [_post("at://1", "Gilmar Mendes vota em MT usando celular em cabine")]
    )
    await harvester.run()

    assert await harvester.release_one() is True
    post, verdict = pipeline.calls[0]
    assert post.uri == "at://1"
    assert verdict.label == VerdictLabel.FALSE
    assert verdict.claim == "Gilmar Mendes vota com celular na cabine"
    assert verdict.evidences == [CHECK]
    assert "claim_harvest" in verdict.agent_outputs
    assert repo.upserts[0]["source"] == "claim_harvest"
    assert await harvester.release_one() is False


@pytest.mark.anyio
async def test_same_post_is_not_harvested_twice():
    harvester, _, _, _ = _harvester(
        [_post("at://1", "Gilmar Mendes vota usando celular na cabine")]
    )
    await harvester.run()
    await harvester.run()
    assert len(harvester.backlog) == 1


@pytest.mark.anyio
async def test_true_checks_are_ignored():
    true_check = Evidence(
        source="google_factcheck",
        url="u",
        title="t",
        snippet="Checagem por Lupa: Gilmar Mendes vota com celular na cabine",
        rating="Verdadeiro",
    )
    harvester, _, _, _ = _harvester(
        [_post("at://1", "Gilmar Mendes vota usando celular na cabine")], evidences=[true_check]
    )
    report = await harvester.run()
    assert report["claims"] == 0


@pytest.mark.anyio
async def test_repeated_spam_text_enters_once():
    text = "Gilmar Mendes vota usando celular na cabine, compartilhem"
    harvester, _, _, _ = _harvester([_post("at://1", text), _post("at://2", text)])
    report = await harvester.run()
    assert report["new_candidates"] == 1


def test_query_terms_keep_numbers():
    from app.domain.factcheck_claims import rare_query_terms

    terms = rare_query_terms(
        "Flávio Bolsonaro ganhou no 1º turno com 54,98%", {"flávio": 900, "bolsonaro": 800}
    )
    assert "54,98" in terms


def test_weighted_coverage_ignores_common_names():
    from app.domain.factcheck_claims import weighted_coverage

    df = {"flávio": 900, "bolsonaro": 900, "ganhou": 300}
    claim = "Flávio Bolsonaro ganhou no 1º turno com 54,98%"
    assert weighted_coverage("Flávio Bolsonaro ganhou a eleição", claim, df, 1000) < 0.3
    assert weighted_coverage("Flávio ganhou no 1º turno com 54,98%", claim, df, 1000) > 0.8


@pytest.mark.anyio
async def test_debunk_with_cross_or_checker_link_is_dropped():
    harvester, _, _, _ = _harvester(
        [
            _post("at://1", "❌ Gilmar Mendes não vota com celular na cabine"),
            _post("at://2", "Gilmar Mendes vota com celular na cabine www.aosfatos.org/noticias/x"),
        ]
    )
    report = await harvester.run()
    assert report["new_candidates"] == 0


class FakeNLI:
    async def predict_nli_batch(self, pairs):
        return [
            {"contradiction": 0.9 if "não usou" in premise else 0.1, "entailment": 0.0}
            for premise, _ in pairs
        ]


@pytest.mark.anyio
async def test_post_that_contradicts_the_false_claim_is_dropped():
    harvester, _, _, _ = _harvester(
        [
            _post("at://1", "Gilmar Mendes não usou celular na cabine de votação"),
            _post("at://2", "Gilmar Mendes vota com celular na cabine, que absurdo"),
        ]
    )
    harvester.classifier = FakeNLI()
    await harvester.run()
    assert [c.post.uri for c in harvester.backlog] == ["at://2"]


@pytest.mark.anyio
async def test_at_most_n_candidates_per_claim():
    extras = ["absurdo", "vergonha", "escândalo", "ridículo", "inacreditável", "lamentável"]
    posts = [
        _post(f"at://{i}", f"Gilmar Mendes vota com celular na cabine, {word}")
        for i, word in enumerate(extras)
    ]
    harvester, _, _, _ = _harvester(posts)
    await harvester.run()
    assert len(harvester.backlog) == harvester.settings.claim_harvest_max_per_claim


@pytest.mark.anyio
async def test_run_forever_survives_a_failing_round(monkeypatch):
    import asyncio

    harvester, _, _, _ = _harvester([])
    calls = {"n": 0}

    async def flaky():
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("bluesky fora")
        raise asyncio.CancelledError

    async def no_sleep(_):
        return None

    monkeypatch.setattr(harvester, "run", flaky)
    monkeypatch.setattr(asyncio, "sleep", no_sleep)
    with pytest.raises(asyncio.CancelledError):
        await harvester.run_forever()
    assert calls["n"] == 2
