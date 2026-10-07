import pytest

from app.domain import geo


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("Resultado em Itacoatiara (AM): votação", {("itacoatiara", "AM")}),
        ("48ª zona eleitoral (Maribondo/AL)", {("maribondo", "AL")}),
        ("Lula (PT) foi o mais votado", set()),  # sigla de partido não é UF de município
        ("Itacoatiara (SP)", set()),  # município não existe nessa UF
        ("Bom Jesus e Campos", set()),  # nomes ambíguos sem UF ficam de fora
        ("Moro em Santos", {("santos", "SP")}),  # nome único + preposição de lugar
        ("Alta Floresta D'Oeste (RO)", {("alta floresta d oeste", "RO")}),
        ("sem localidade nenhuma", set()),
    ],
)
def test_places(texto, esperado):
    assert geo.places(texto) == esperado


def test_zones():
    assert geo.zones("3ª zona e 48a zona eleitoral") == {"3", "48"}
    assert geo.zones("sem zona") == frozenset()


def test_places_conflict_so_com_os_dois_lados_e_sem_nada_em_comum():
    itacoatiara = geo.places("Itacoatiara (AM)")
    maribondo = geo.places("Maribondo/AL")
    assert geo.places_conflict(itacoatiara, maribondo)
    assert not geo.places_conflict(itacoatiara, itacoatiara | maribondo)
    assert not geo.places_conflict(itacoatiara, frozenset())
    assert not geo.places_conflict(frozenset(), maribondo)
    muitas = frozenset((f"cidade{i}", "AM") for i in range(4))
    assert not geo.places_conflict(itacoatiara, muitas)
