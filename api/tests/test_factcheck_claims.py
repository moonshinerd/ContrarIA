import pytest

from app.domain.entities import Evidence
from app.domain.factcheck_claims import (
    RatingKind,
    checked_claim,
    claim_keywords,
    distinctive_tokens,
    rating_kind,
)


@pytest.mark.parametrize(
    ("rating", "kind"),
    [
        ("falso", RatingKind.FALSE),
        ("Falso", RatingKind.FALSE),
        ("Errado", RatingKind.FALSE),
        ("Enganoso", RatingKind.MISLEADING),
        ("Fora de contexto", RatingKind.MISLEADING),
        ("não_é_bem_assim", RatingKind.MISLEADING),
        ("Verdadeiro", RatingKind.TRUE),
        ("É #FATO", RatingKind.TRUE),
        ("", None),
        (None, None),
        ("em análise", None),
    ],
)
def test_rating_kind(rating, kind):
    assert rating_kind(rating) == kind


def test_google_factcheck_claim_comes_from_snippet_and_rating():
    evidence = Evidence(
        source="google_factcheck",
        url="https://aosfatos.org/x",
        title="Não é verdade que policiais encontraram urna fraudada no DF",
        snippet="Checagem por Aos Fatos: PMs descobriram uma urna eletrônica fraudada no DF",
        rating="falso",
    )
    assert checked_claim(evidence) == (
        "PMs descobriram uma urna eletrônica fraudada no DF",
        RatingKind.FALSE,
    )


def test_google_factcheck_without_known_rating_is_ignored():
    evidence = Evidence(
        source="google_factcheck", url="u", title="t", snippet="Checagem por X: algo", rating="?"
    )
    assert checked_claim(evidence) is None


def test_rss_title_with_explicit_claim():
    evidence = Evidence(
        source="rss_checkers",
        url="u",
        title="É falso que Flávio Bolsonaro teve 54,98% no 1º turno 12/10/2026 18h11",
        snippet="",
    )
    assert checked_claim(evidence) == ("Flávio Bolsonaro teve 54,98% no 1º turno", RatingKind.FALSE)


def test_rss_title_that_states_the_truth_does_not_yield_a_claim():
    evidence = Evidence(
        source="rss_checkers", url="u", title="Lula não chorou ao falar sobre Flávio", snippet=""
    )
    assert checked_claim(evidence) is None


def test_distinctive_tokens_are_names_and_numbers():
    assert distinctive_tokens("Flávio Bolsonaro teve 54,98% no 1º turno") == [
        "flávio",
        "bolsonaro",
        "54,98%",
        "1º",
    ]


def test_claim_keywords_prefers_specific_terms():
    query = claim_keywords("Urna em Mato Grosso com 100% dos votos válidos para Lula prova fraude")
    assert query is not None
    assert query.split()[:2] == ["urna", "mato"]
    assert len(query.split()) <= 4


def test_claim_keywords_needs_two_terms():
    assert claim_keywords("É falso") is None


def test_debunking_posts_are_recognized():
    from app.domain.factcheck_claims import looks_like_debunk

    assert looks_like_debunk("É falso que Gilmar Mendes entrou na cabine de votação com celular")
    assert looks_like_debunk("VOTO SEM FAKE. Não é verdade que o Exército comunicou ao STF")
    assert looks_like_debunk("Isso é boato, o TSE já desmentiu")
    assert not looks_like_debunk("Gilmar Mendes entrou na cabine de votação com celular")


def test_claim_coverage_rewards_repeating_the_content_not_just_the_name():
    from app.domain.factcheck_claims import claim_coverage

    checked = "Lula jogou bandeira do Brasil no chão após votar"
    assert claim_coverage("Lula jogou a bandeira do Brasil no chão depois de votar", checked) > 0.7
    assert claim_coverage("LULA 13: promoveu avanços na vida do povo brasileiro", checked) < 0.5
