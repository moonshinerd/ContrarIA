import pytest

from app.domain.sentences import split_sentences


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        (
            "Votação no E. M. Dom Pedro I, na 3ª zona eleitoral",
            ["Votação no E. M. Dom Pedro I, na 3ª zona eleitoral"],
        ),
        (
            "Votação no E.E.I.E.F. Cristiano Nunes, na 120ª zona",
            ["Votação no E.E.I.E.F. Cristiano Nunes, na 120ª zona"],
        ),
        (
            "O Sen. Fulano disse que o Min. Beltrano errou. Isso foi ontem. A Dra. Maria concorda.",
            [
                "O Sen. Fulano disse que o Min. Beltrano errou.",
                "Isso foi ontem.",
                "A Dra. Maria concorda.",
            ],
        ),
        (
            "A pesquisa ouviu 2.000 pessoas em 5 de out. de 2026. Lula tem 39%.",
            ["A pesquisa ouviu 2.000 pessoas em 5 de out. de 2026.", "Lula tem 39%."],
        ),
        (
            "Isso é um absurdo! Ninguém merece... Vamos ver? Sim.",
            ["Isso é um absurdo!", "Ninguém merece...", "Vamos ver?", "Sim."],
        ),
        ("", []),
        ("Sem pontuação final", ["Sem pontuação final"]),
    ],
)
def test_split_sentences(texto, esperado):
    assert split_sentences(texto) == esperado
