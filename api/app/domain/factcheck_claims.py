"""Alegação checada, nota da checagem e palavras-chave de busca.

Funções puras usadas pelo Jev (casamento post x checagem) e pelo coletor (busca ativa).
Só extraímos a alegação quando ela é explícita: o `claim.text` do Google Fact Check ou
títulos no formato "É falso que X". Títulos que já afirmam o contrário da alegação
("Lula não chorou...") não servem: inferir a alegação original seria adivinhar.
"""

import math
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
    "desde até ate sem sob ao aos à às de do da em no na um e o a os as ou se já "
    "aqui agora hoje ontem amanhã ainda sempre nunca nada tudo todo isso aquilo então "
    "assim bem muito pouco mais menos vamos vai vou sendo seria será fazer feito "
    "você vocês voce voces gente".split()
)
_TOKEN = re.compile(r"\d+(?:[.,]\d+)*%?º?|[\wÀ-ÿ$]+", re.UNICODE)
_ACRONYM = re.compile(r"^[A-ZÁÀÂÃÉÊÍÓÔÕÚÇ]{2,6}$")
_PROPER = re.compile(r"^[A-ZÁÀÂÃÉÊÍÓÔÕÚÇ][a-záàâãéêíóôõúç]{2,}$")


_DEBUNK_MARKERS = re.compile(
    r"\b(?:"
    r"[eé]\s+(?:#?fake|fals[oa])|"
    r"fals[oa]\s+que|"
    r"n[aã]o\s+[eé]\s+(?:verdade|fato)|"
    r"fake\s*news|"
    r"fato\s+ou\s+fake|"
    r"mentira|"
    r"ment(?:e|em|iu|iram|indo)\s+(?:ao\s+(?:dizer|afirmar|alegar|declarar|publicar)|dizendo|que)|"
    r"boato|"
    r"desment\w+|"
    r"checagem|checamos|fact[\s-]?check|"
    r"n[aã]o\s+(?:foi|houve|existe|aconteceu)|"
    r"voto\s+sem\s+fake|bsfato|posts?\s+falsos?|"
    r"gerada\s+por\s+intelig[eê]ncia\s+artificial|"
    r"usad[oa]\s+para\s+alegar|"
    r"fora\s+de\s+contexto"
    r")\b"
    r"|#fake\b|^no\s+ar\.",
    re.IGNORECASE,
)


_CHECKER_LINKS = re.compile(
    r"aosfatos\.org|estadao-verifica|lupa\.uol|agencialupa|fato-ou-fake|boatos\.org|"
    r"projetocomprova|checamos\.afp|noticias\.uol\.com\.br/confere",
    re.IGNORECASE,
)

_NUMERIC_ANCHOR_PATTERN = re.compile(r"\b\d+(?:[.,]\d+)*(?:\s*%)?", re.UNICODE)


def _canonical_number(token: str) -> str:
    s = token.strip()
    s = re.sub(r"[%ºª\s]", "", s)
    if not s:
        return ""
    if "." in s and "," in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    if re.search(r"^\d{1,3}(?:\.\d{3})+$", s):
        s = s.replace(".", "")
    elif s.endswith(".0"):
        s = s[:-2]
    return s


def numeric_anchors(text: str) -> set[str]:
    """Extrai números normalizados de um texto (sem %, normalizando pontos e vírgulas)."""
    anchors: set[str] = set()
    for match in _NUMERIC_ANCHOR_PATTERN.findall(text):
        canon = _canonical_number(match)
        if canon:
            anchors.add(canon)
    return anchors


def covers_numeric_anchors(post_text: str, claim: str) -> bool:
    """Verifica se o post contém todas as âncoras numéricas da alegação checada."""
    required = numeric_anchors(claim)
    if not required:
        return True
    present = numeric_anchors(post_text)
    return required.issubset(present)


def looks_like_debunk(text: str) -> bool:
    """O texto já desmente ou comenta uma alegação (não a afirma): "É falso que...", "boato",
    "❌ Fulano não disse...", ou um link para a própria checagem."""
    return bool(_DEBUNK_MARKERS.search(text) or "❌" in text or _CHECKER_LINKS.search(text))


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


# Palavras que aparecem em quase toda alegação eleitoral e não a distinguem de outras.
_GENERIC_QUERY_TERMS = frozenset(
    "vídeo video mostra foto imagem diz disse afirma presidente governo eleição eleições "
    "eleitoral turno segundo primeiro campanha candidato publicou noticiou post posts durante "
    "após antes brasil brasileiro brasileiros urgente agora".split()
)


def rare_query_terms(claim: str, document_frequency: dict[str, int], limit: int = 2) -> list[str]:
    """Termos mais raros da alegação no corpus de posts: o que a distingue no searchPosts.

    Nomes comuns ("Lula", "Flávio") trazem milhares de posts sem relação; termos raros
    ("milho", "pelinho", "padroeira") trazem quem repete aquela alegação específica.
    """
    terms: list[str] = []
    for token in informative_tokens(claim):
        # Números ("54,98%", "61%") são o termo mais distintivo de muitas alegações.
        term = token.rstrip("%º")
        if term not in _GENERIC_QUERY_TERMS and term not in terms and len(term) >= 2:
            terms.append(term)
    terms.sort(key=lambda t: (document_frequency.get(t, 0), -len(t)))
    return terms[:limit]


def _content_tokens(text: str) -> list[str]:
    """Palavras informativas mais números de qualquer tamanho ("61%" vira "61")."""
    tokens = list(informative_tokens(text))
    for token in _TOKEN.findall(text):
        number = token.rstrip("%º")
        if number[:1].isdigit() and number not in tokens:
            tokens.append(number)
    return tokens


def weighted_coverage(
    post: str, checked: str, document_frequency: dict[str, int], corpus_size: int
) -> float:
    """Cobertura da alegação ponderada pela raridade (IDF) de cada palavra.

    Na cobertura simples, "Flávio Bolsonaro ganhou" cobre 60% de "Flávio Bolsonaro ganhou no
    1º turno com 54,98%" sem dizer nada dela; aqui os nomes comuns quase não pesam.
    """
    wanted = _content_tokens(checked)
    if len(wanted) < 2:
        return 0.0
    have = {t[:5] for t in _content_tokens(post)}

    def idf(token: str) -> float:
        return math.log((corpus_size + 1) / (document_frequency.get(token, 0) + 1))

    total = sum(idf(t) for t in wanted)
    if total <= 0:
        return 0.0
    return sum(idf(t) for t in wanted if t[:5] in have) / total


_PUBLISHER_BY_HOST = {
    "aosfatos.org": "Aos Fatos",
    "lupa.uol.com.br": "Lupa",
    "agencialupa.org": "Lupa",
    "g1.globo.com": "g1 Fato ou Fake",
    "estadao.com.br": "Estadão Verifica",
    "noticias.uol.com.br": "UOL Confere",
    "boatos.org": "Boatos.org",
    "projetocomprova.com.br": "Comprova",
    "checamos.afp.com": "AFP Checamos",
}
_SNIPPET_PUBLISHER = re.compile(r"^Checagem por ([^:]+):", re.IGNORECASE)


def publisher_name(evidence: Evidence) -> str:
    """Nome da agência que fez a checagem (do snippet do Google ou do domínio da URL)."""
    match = _SNIPPET_PUBLISHER.match((evidence.snippet or "").strip())
    if match:
        return match.group(1).strip()
    host = re.sub(r"^https?://(?:www\.)?([^/]+).*$", r"\1", evidence.url or "")
    return _PUBLISHER_BY_HOST.get(host, host or "uma agência de checagem")
