"""Alegação checada, nota da checagem e palavras-chave de busca.

Funções puras usadas pelo Jev (casamento post x checagem) e pelo coletor (busca ativa).
Só extraímos a alegação quando ela é explícita: o `claim.text` do Google Fact Check ou
títulos no formato "É falso que X". Títulos que já afirmam o contrário da alegação
("Lula não chorou...") não servem: inferir a alegação original seria adivinhar.
"""

import re
from enum import StrEnum

from app.domain.entities import Evidence


class RatingKind(StrEnum):
    FALSE = "false"
    MISLEADING = "misleading"
    TRUE = "true"


_MISLEADING = re.compile(
    r"engano|fora\s+de\s+contexto|distor[cç]|n[aã]o[\s_]+[eé][\s_]+bem[\s_]+assim|exager"
    r"|descontextualiz|impreciso|parcialmente|sem\s+contexto|alterad",
    re.IGNORECASE,
)
_FALSE = re.compile(
    r"\bfalso|\bfalsa\b|#?fake|errado|boato|mentira|montagem|inventad|incorret|"
    r"n[aã]o\s+[eé]\s+verdade|sem\s+provas|n[aã]o\s+procede|golpe",
    re.IGNORECASE,
)
_TRUE = re.compile(
    r"\bverdadeiro|\bverdadeira|\bcorreto|[eé]\s+(?:#)?fato\b|\bfato\b", re.IGNORECASE
)

_PUBLISHER_PREFIX = re.compile(r"^Checagem por [^:]+:\s*", re.IGNORECASE)
_EXPLICIT_CLAIM = re.compile(
    r"^(?:\d+\.\s*)?(?:[eé]\s+(?:#?fake|fals[oa]|enganos[oa])|n[aã]o\s+[eé]\s+verdade)\s+que\s+(.+)$",
    re.IGNORECASE,
)
_TRAILING_DATE = re.compile(r"\s+\d{2}/\d{2}/\d{4}.*$")
_STOPWORDS = frozenset(
    "para como mais mas que com uma uns umas dos das nos nas pelo pela pelos pelas ele ela "
    "eles elas isso esse essa esses essas este esta estes estas seu sua seus suas por não "
    "nao sobre entre depois antes quando onde porque pois ser foi são sao tem têm ter vai "
    "vão vao está estao estão disse diz sido caso após ainda também tambem muito muita "
    "novo nova mesmo mesma outro outra todo toda todos todas qual quais cada nesta neste "
    "desde até ate sem sob ao aos à às de do da em no na um e o a os as ou se já".split()
)
_TOKEN = re.compile(r"\d+(?:[.,]\d+)*%?º?|[\wÀ-ÿ$]+", re.UNICODE)
_ACRONYM = re.compile(r"^[A-ZÁÀÂÃÉÊÍÓÔÕÚÇ]{2,6}$")
_PROPER = re.compile(r"^[A-ZÁÀÂÃÉÊÍÓÔÕÚÇ][a-záàâãéêíóôõúç]{2,}$")


_DEBUNK_MARKERS = re.compile(
    r"\b(?:[eé]\s+(?:#?fake|fals[oa])|n[aã]o\s+[eé]\s+verdade|fake\s*news|fato\s+ou\s+fake|"
    r"mentira|boato|desmentid|desmente|checagem|checamos|fact[\s-]?check|"
    r"n[aã]o\s+(?:foi|houve|existe|aconteceu)|voto\s+sem\s+fake)\b|#fake\b",
    re.IGNORECASE,
)


def looks_like_debunk(text: str) -> bool:
    """O texto já desmente ou comenta uma alegação (não a afirma): "É falso que...", "boato"."""
    return bool(_DEBUNK_MARKERS.search(text))


def rating_kind(rating: str | None) -> RatingKind | None:
    """Classifica a nota crua da checagem. Enganoso vence falso ("falso e enganoso")."""
    if not rating:
        return None
    text = rating.replace("_", " ")
    if _MISLEADING.search(text):
        return RatingKind.MISLEADING
    if _FALSE.search(text):
        return RatingKind.FALSE
    if _TRUE.search(text):
        return RatingKind.TRUE
    return None


def checked_claim(evidence: Evidence) -> tuple[str, RatingKind] | None:
    """Alegação que a checagem avaliou e a nota dada a ela, ou None se não for explícita."""
    snippet = (evidence.snippet or "").strip()
    if evidence.source == "google_factcheck":
        claim = _PUBLISHER_PREFIX.sub("", snippet).strip()
        kind = rating_kind(evidence.rating)
        return (claim, kind) if claim and kind else None

    title = _TRAILING_DATE.sub("", (evidence.title or "").strip()).strip()
    match = _EXPLICIT_CLAIM.match(title)
    if not match:
        return None
    claim = match.group(1).strip(" .")
    marker = title[: match.start(1)]
    kind = rating_kind(marker) or RatingKind.FALSE
    return (claim, kind) if len(claim) >= 12 else None


def informative_tokens(text: str) -> list[str]:
    """Tokens com conteúdo (sem stopwords), na ordem do texto, sem repetição."""
    seen: list[str] = []
    for token in _TOKEN.findall(text):
        key = token.casefold()
        if len(key) >= 4 and key not in _STOPWORDS and key not in seen:
            seen.append(key)
    return seen


def distinctive_tokens(text: str) -> list[str]:
    """Nomes próprios e números do texto: o que torna uma alegação específica."""
    out: list[str] = []
    for token in _TOKEN.findall(text):
        key = token.casefold()
        if key in out or key in _STOPWORDS:
            continue
        if _PROPER.match(token) or _ACRONYM.match(token) or any(ch.isdigit() for ch in token):
            out.append(key)
    return out


def claim_keywords(claim: str, limit: int = 4) -> str | None:
    """Consulta curta para o searchPosts (que exige todos os termos): o específico primeiro."""
    distinctive = distinctive_tokens(claim)
    rest = [t for t in informative_tokens(claim) if t not in distinctive and len(t) >= 5]
    terms = (distinctive + rest)[:limit]
    return " ".join(terms) if len(terms) >= 2 else None


def claim_coverage(post_sentence: str, checked: str) -> float:
    """Fração do conteúdo da alegação checada que o post também diz (compara por radical)."""
    wanted = informative_tokens(checked)
    if not wanted:
        return 0.0
    have = {t[:5] for t in informative_tokens(post_sentence)}
    return sum(1 for t in wanted if t[:5] in have) / len(wanted)
