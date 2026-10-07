"""Localidades citadas em um texto, com gazetteer dos municípios do IBGE.

Serve para desambiguar entidades homônimas: "E. M. Dom Pedro I" existe em Itacoatiara (AM) e em
Maribondo (AL), e uma evidência sobre uma não prova nada sobre a outra. Seguimos o que a literatura
de geoparsing recomenda: um gazetteer, o contexto hierárquico cidade + UF e o princípio de "um
sentido por discurso" (a localidade vale para o post inteiro, não só para o fragmento verificado).

Dados: `data/municipios_br.json`, gerado por `app/scripts/build_gazetteer.py` a partir do IBGE.
Função pura, sem I/O além de ler o arquivo uma vez.
"""

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

_DATA_FILE = Path(__file__).parent / "data" / "municipios_br.json"

# Nomes de estado que também são prefixo de município ("Rio Grande", "São Paulo"): não contam
# como cidade quando aparecem sozinhos no sentido de estado.
_STATE_NAMES = frozenset(
    "acre alagoas amapa amazonas bahia ceara distrito federal espirito santo goias maranhao "
    "mato grosso minas gerais para paraiba parana pernambuco piaui rio de janeiro grande norte sul "
    "rondonia roraima santa catarina sao paulo sergipe tocantins".split()
)
_LOCATIVE_CUES = frozenset({"em", "de", "do", "da", "dos", "das", "no", "na", "nos", "nas"})
_CONNECTORS = frozenset({"de", "da", "do", "dos", "das", "e", "d"})
_WORD = re.compile(r"[\wÀ-ÿ'’]+")
_UF_AFTER = re.compile(r"\s*(?:\(|/|,|-|–)\s*([A-Z]{2})\b")
_ZONE = re.compile(r"\b(\d{1,3})\s*[ªaº°]?\s*zona", re.IGNORECASE)


def normalize(text: str) -> str:
    """Minúsculas, sem acento nem pontuação interna, espaços colapsados."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    plain = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(re.sub(r"['’\-]", " ", plain).split())


@lru_cache(maxsize=1)
def _gazetteer() -> tuple[dict[str, frozenset[str]], int]:
    """(nome normalizado -> UFs onde existe município com esse nome, maior nº de palavras)."""
    by_name: dict[str, set[str]] = {}
    for uf, names in json.loads(_DATA_FILE.read_text(encoding="utf-8")).items():
        for name in names:
            by_name.setdefault(normalize(name), set()).add(uf)
    longest = max(len(name.split()) for name in by_name)
    return {name: frozenset(ufs) for name, ufs in by_name.items()}, longest


def places(text: str) -> frozenset[tuple[str, str]]:
    """Pares (município normalizado, UF) citados no texto.

    - Com marcador de UF ("Itacoatiara (AM)", "Maribondo/AL"): vale se o município existe naquela UF
      (então "Lula (PT)" não vira lugar).
    - Sem UF: só quando o nome é único no país e vem em maiúscula, e ou tem mais de uma palavra ou
      é precedido de preposição de lugar ("em Itacoatiara"). Nomes ambíguos ficam de fora.
    """
    index, longest = _gazetteer()
    words = list(_WORD.finditer(text))
    found: set[tuple[str, str]] = set()
    i = 0
    while i < len(words):
        if not words[i].group()[:1].isupper():
            i += 1
            continue
        matched = False
        for size in range(min(longest, len(words) - i), 0, -1):
            span = words[i : i + size]
            inner = [w.group() for w in span[1:-1]]
            if any(not (w.casefold() in _CONNECTORS or w[:1].isupper()) for w in inner):
                continue
            if not span[-1].group()[:1].isupper():
                continue
            name = normalize(text[span[0].start() : span[-1].end()])
            ufs = index.get(name)
            if not ufs or name in _STATE_NAMES:
                continue
            uf_match = _UF_AFTER.match(text, span[-1].end())
            if uf_match and uf_match.group(1) in ufs:
                found.add((name, uf_match.group(1)))
            elif len(ufs) == 1 and (
                size > 1 or (i > 0 and words[i - 1].group().casefold() in _LOCATIVE_CUES)
            ):
                found.add((name, next(iter(ufs))))
            else:
                continue
            i += size
            matched = True
            break
        if not matched:
            i += 1
    return frozenset(found)


def zones(text: str) -> frozenset[str]:
    """Números de zona eleitoral citados ("3ª zona", "48a zona")."""
    return frozenset(_ZONE.findall(text))


def places_conflict(
    context: frozenset[tuple[str, str]],
    evidence: frozenset[tuple[str, str]],
    *,
    max_evidence_places: int = 3,
) -> bool:
    """A evidência fala de outro lugar que o contexto?

    Só conclui conflito quando os dois lados citam localidades e não há nenhuma em comum. Uma
    matéria que lista muitas localidades (nacional ou regional) não é tratada como "outro lugar".
    """
    if not context or not evidence or len(evidence) > max_evidence_places:
        return False
    return context.isdisjoint(evidence)
