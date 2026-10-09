"""Verificação via classificação local (Jev) em vez de debate multiagente na
nuvem: mesmas fontes de evidência de sempre, mas quem decide relevância,
suporte e o veredito final é o modelo local (logprobs, sem JSON). O LLM na
nuvem não participa desta etapa -- só é chamado depois, em intervention.py,
pra escrever o texto da resposta socrática citando a evidência já reunida
aqui.

Reaproveita a mesma tabela/mecanismo de calibração CRC do backend "llm"
(app/services/crc.py), só que com uma chave de modelo própria ("jev:<repo>:
<file>"), pra não misturar as distribuições de confiança dos dois backends.

Validado ao vivo contra 2 posts reais (28/09/2026) e ajustado a partir dos
problemas encontrados:
- Tratar o post inteiro como "a alegação" perde números/fatos específicos
  embutidos em texto opinativo (ex.: "220 deputados... em 513" dentro de um
  desabafo retórico) -- agora o post é dividido em frases candidatas e cada
  uma é classificada (e verificada) separadamente.
- Buscar evidência usando o texto bruto do post (com URL, quebras de linha)
  trazia resultado genérico/fora do tema -- a busca agora usa só a frase
  específica sendo verificada, com URLs removidas.
- O julgamento de relevância binário simples marcava quase tudo como
  "relevante" -- agora exige uma margem mínima entre relevante/irrelevante
  e o prompt é explícito sobre exigir os mesmos fatos/pessoas/números, não
  só o mesmo tema genérico (ex.: "eleição").
"""

import asyncio
import json
import logging
import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from urllib.parse import urlparse

from sqlalchemy import create_engine

from app.clients.articles import fetch_article_text
from app.clients.evidence import get_evidence_source
from app.clients.evidence.base import EvidenceSource
from app.clients.evidence.google_factcheck import GoogleFactCheckClient
from app.clients.evidence.web_search import is_valid_evidence_url
from app.core.config import Settings, get_settings
from app.domain import geo
from app.domain.entities import Evidence, Post, Verdict, VerdictLabel
from app.domain.sentences import split_sentences
from app.models.classifiers.jev import (
    PROMPT_OVERHEAD_TOKENS,
    JevClassifierPort,
    get_jev_classifier,
)
from app.repositories.crc_calibration import CRCCalibrationRepository

logger = logging.getLogger("contraria.services.jev_verification")

# Perguntar "o que as evidências dizem" em vez de "é verdadeira, falsa ou
# enganosa": com a definição de "enganosa" na pergunta, o modelo escolhia essa
# opção com ~100% até para fatos confirmados e para falsos, nas duas ordens.
# Com esta formulação acertou 4 de 4 casos de teste, também nas duas ordens.
_LABEL_BY_OPTION = {
    "confirmam a alegação": VerdictLabel.TRUE,
    "desmentem a alegação": VerdictLabel.FALSE,
    "confirmam o fato, mas desmentem a conclusão ou o exagero da alegação": (
        VerdictLabel.MISLEADING
    ),
    "as evidências são insuficientes ou não tratam da alegação": (
        VerdictLabel.INSUFFICIENT_EVIDENCE
    ),
}
_MAX_CANDIDATE_CLAIMS = 6
_MIN_SENTENCE_LEN = 15
_RELEVANCE_MARGIN = 0.15
# URLs com esquema, com www e também domínio solto ("x.com/fulano/st...").
_URL_PATTERN = re.compile(
    r"https?://\S+|\bwww\.\S+|\b[\w-]+(?:\.[\w-]+)*\.[a-z]{2,}/\S*", re.IGNORECASE
)
# Cada chamada ao modelo é um prompt lido inteiro em CPU: menos evidências e
# matéria mais curta são o que mais reduz o tempo por post.
_MAX_EVIDENCE_FOR_RELEVANCE = 8
# O veredito recebe matérias completas até encher o contexto do modelo
# (contado com o tokenizador dele); as que não cabem inteiras entram só com o
# trecho da busca.
_MAX_EVIDENCE_FOR_VERDICT = 5
_ARTICLE_MAX_CHARS = 8000
# Links citados pelo próprio post lidos como evidência (ver `_cited_evidence`).
_MAX_CITED_LINKS = 2
# Trechos da matéria citada comparados com a alegação pelo NLI (título + janelas de 2 frases).
_MAX_NLI_CHUNKS = 12
_CHUNK_MAX_CHARS = 600
_SNIPPET_MAX_CHARS = 400
_WORD_PATTERN = re.compile(r"\w{4,}")
# Uma coincidência isolada (sobretudo cidade, país ou tema amplo) não mostra
# que a fonte trata da mesma alegação. Ex.: uma página que menciona Barcelona
# não é evidência sobre um evento específico ocorrido em Barcelona.
_MIN_DIRECT_ANCHOR_OVERLAP = 2
_TEMPORAL_REFERENCE_PATTERN = re.compile(
    r"(?<!at[eé]\s)(?<!de\s)\b"
    r"(hoje|ontem|amanh[ãa]|agora|acaba de|esta semana|nesta semana|neste m[eê]s)\b",
    re.IGNORECASE,
)
_NAME_WORD = r"[A-ZÁÀÂÃÉÊÍÓÔÕÚÇ][a-záàâãéêíóôõúç]+"
_CANDIDATE_CLAIM_PATTERN = re.compile(
    rf"(?P<name>{_NAME_WORD}(?:\s+(?:d[aeo]s?|{_NAME_WORD})){{1,4}})"
    r"\s*,?\s*(?:que\s+)?(?:nesta\s+elei[çc][ãa]o\s+)?"
    r"concorre\s+a[o]?\s+senad",
)
_SENATE_CANDIDATE_PATTERN = re.compile(r"candidat[oa]s?\s+ao\s+senado", re.IGNORECASE)
_NEGATION_PATTERN = re.compile(
    r"\b(n[ãa]o|falso|boato|desistiu|impugnada|impugnado)\b", re.IGNORECASE
)

# Palavras funcionais, verbos e substantivos genéricos que não devem contar
# como âncoras informativas isoladas (evita que 'começou a cair' dê match
# com matérias de tempestades e telhados quando a frase é metafórica).
_PORTUGUESE_STOPWORDS = {
    "a",
    "o",
    "os",
    "as",
    "um",
    "uma",
    "uns",
    "umas",
    "de",
    "do",
    "da",
    "dos",
    "das",
    "em",
    "no",
    "na",
    "nos",
    "nas",
    "por",
    "para",
    "pra",
    "com",
    "sem",
    "sob",
    "sobre",
    "entre",
    "ate",
    "até",
    "e",
    "ou",
    "mas",
    "porem",
    "porém",
    "contudo",
    "todavia",
    "que",
    "se",
    "como",
    "quando",
    "onde",
    "porque",
    "por que",
    "qual",
    "quais",
    "quem",
    "este",
    "esta",
    "estes",
    "estas",
    "esse",
    "essa",
    "esses",
    "essas",
    "aquele",
    "aquela",
    "aqueles",
    "aquelas",
    "isto",
    "isso",
    "aquilo",
    "ele",
    "ela",
    "eles",
    "elas",
    "dele",
    "dela",
    "deles",
    "delas",
    "seu",
    "sua",
    "seus",
    "suas",
    "meu",
    "minha",
    "nosso",
    "nossa",
    "foi",
    "foram",
    "era",
    "eram",
    "ser",
    "sendo",
    "sido",
    "é",
    "sao",
    "são",
    "ter",
    "tinha",
    "tinham",
    "teve",
    "tiveram",
    "tem",
    "têm",
    "estar",
    "estava",
    "estavam",
    "esteve",
    "estiveram",
    "está",
    "estao",
    "estão",
    "fazer",
    "fez",
    "fizeram",
    "faz",
    "fazem",
    "dizer",
    "disse",
    "disseram",
    "diz",
    "dizem",
    "ir",
    "vai",
    "vao",
    "vão",
    "dar",
    "deu",
    "deram",
    "dá",
    "dao",
    "dão",
    "ficar",
    "ficou",
    "ficaram",
    "fica",
    "ficam",
    "comecar",
    "começar",
    "comecou",
    "começou",
    "comecam",
    "começam",
    "cair",
    "caiu",
    "cai",
    "caem",
    "casa",
    "parte",
    "partes",
    "ponto",
    "pontos",
    "coisa",
    "coisas",
    "gente",
    "pessoas",
    "pessoa",
    "mundo",
    "brasil",
    "hoje",
    "ontem",
    "amanha",
    "amanhã",
    "agora",
    "depois",
    "antes",
    "sempre",
    "nunca",
    "ja",
    "já",
    "ainda",
    "mais",
    "menos",
    "muito",
    "muitos",
    "muita",
    "muitas",
    "pouco",
    "poucos",
    "pouca",
    "poucas",
    "todo",
    "toda",
    "todos",
    "todas",
    "tudo",
    "nada",
    "outro",
    "outra",
    "outros",
    "outras",
    "mesmo",
    "mesma",
    "mesmos",
    "mesmas",
    "assim",
    "entao",
    "então",
    "apenas",
    "somente",
    "tambem",
    "também",
    "alem",
    "além",
    "bem",
    "mal",
    "segundo",
    "conforme",
    "durante",
    "desde",
    "contra",
    "maior",
    "menor",
    "primeiro",
    "primeira",
    "novo",
    "nova",
    "novos",
    "novas",
    "ano",
    "anos",
    "dia",
    "dias",
    "mes",
    "mês",
    "meses",
    "vez",
    "vezes",
    "voce",
    "você",
    "voces",
    "vocês",
    "lembrar",
    "lembra",
    "lembram",
    "lembrem",
    "amigo",
    "amigos",
    "amiga",
    "amigas",
    "festa",
    "festas",
    "festinha",
    "festinhas",
    "intimo",
    "intimos",
    "intima",
    "intimas",
    "íntimo",
    "íntimos",
    "íntima",
    "íntimas",
}

_IDIOM_PATTERNS = re.compile(
    r"\b("
    r"a\s+casa\s+(caiu|vai\s+cair|t[aá]\s+caindo|come[çc]ou\s+a\s+cair)|"
    r"caiu\s+a\s+ficha|cair\s+a\s+ficha|"
    r"a\s+chapa\s+(esquentou|vai\s+esquentar|t[aá]\s+quente)|"
    r"a\s+batata\s+(t[aá]\s+assando|vai\s+assar)|"
    r"dar\s+com\s+os\s+burros\s+n['’]?\s*[aá]gua|"
    r"jogar\s+(a\s+toalha|merda\s+no\s+ventilador)|"
    r"enfiar\s+o\s+p[eé]\s+na\s+jaca|"
    r"pisar\s+em\s+ovos|"
    r"colocar\s+panos\s+quentes|"
    r"puxar\s+o\s+tapete|"
    r"com\s+a\s+corda\s+no\s+pesco[çc]o|"
    r"meter\s+os\s+p[eé]s\s+pelas\s+m[aã]os|"
    r"soltar\s+os\s+cachorros|"
    r"dar\s+o\s+troco|"
    r"sangue\s+nos\s+olhos|"
    r"acorda\s+brasil|"
    r"o\s+circo\s+pegar\s+fogo|"
    r"o\s+bicho\s+vai\s+pegar"
    r")\b",
    re.IGNORECASE,
)

_QUESTION_PATTERN = re.compile(
    r"^(?:[\s\-\*•—–]+\s*)?(o\s+que|quem|quando|onde|por\s*que|por\s*qu[eê]|como|qual|quais|ser[aá]\s+que|voc[eê]s?\s+lembram|voc[eê]s?\s+sabiam|lembra)\b",
    re.IGNORECASE,
)

_TRAILING_CONNECTOR_PATTERN = re.compile(
    r"(?:\s+\b(?:na|no|nas|nos|em|de|da|do|das|dos|para|pra|com|por|que|se|e|ou|mas|a|o|as|os)\b|[,\-:]+|\.\.\.)+\s*$",
    re.IGNORECASE,
)

_METRIC_PATTERN = re.compile(
    r"(?:R\$\s*[\d.,]+|\b\d+(?:[.,]\d+)?\s*(?:%|por\s+cento|mil(?:h[õo]es)?|bilh[õo]es)?\b|\b\d{4}\b)"
)

_POLITICAL_TITLES_PATTERN = re.compile(
    r"\b(ministro|ministra|senador|senadora|deputado|deputada|presidente|presidenta|governador|governadora|prefeito|prefeita|juiz|juíza|desembargador|desembargadora|vereador|vereadora|candidat[oa]s?|relator|relatora)\b",
    re.IGNORECASE,
)

_FACTUAL_PREDICATE_PATTERN = re.compile(
    r"\b(derrubou|suspendeu|anulou|aprovou|rejeitou|votou|prendeu|foi\s+pres[oa]|investigad[oa]|denunciad[oa]|indiciad[oa]|condenad[oa]|processad[oa]|processo|propina|corrup[çc][ãa]o|liminar|decreto|portaria|nota\s+fiscal|notas\s+fiscais|gabinete|reuni[ãa]o|áudios?|prints?|whatsApp|contrato|licita[çc][ãa]o|elei[çc][ãa]o|candidatura)\b",
    re.IGNORECASE,
)

_ALL_CAPS_NAME_PATTERN = re.compile(r"\b([A-ZÁÀÂÃÉÊÍÓÔÕÚÇ]{3,}(?:\s+[A-ZÁÀÂÃÉÊÍÓÔÕÚÇ]{3,}){1,2})\b")
_HEADLINE_TERMS = {
    "formou",
    "formar",
    "garantir",
    "garante",
    "acesso",
    "informacao",
    "informação",
    "eleicoes",
    "eleições",
    "eleicao",
    "eleição",
    "voto",
    "votos",
    "votou",
    "votam",
    "maioria",
    "minoria",
    "urgente",
    "alerta",
    "decidiu",
    "decide",
    "aprovou",
    "aprova",
    "justica",
    "justiça",
    "noticia",
    "notícia",
    "postagem",
    "video",
    "vídeo",
    "foto",
    "fotos",
    "imagem",
    "imagens",
    "audio",
    "áudio",
    "print",
    "prints",
}
_ACRONYM_PATTERN = re.compile(r"\b[A-Z]{2,6}\b")
_PROPER_NOUN_PATTERN = re.compile(
    r"\b[A-ZÁÀÂÃÉÊÍÓÔÕÚÇ][a-záàâãéêíóôõúç]+(?:\s+[A-ZÁÀÂÃÉÊÍÓÔÕÚÇ][a-záàâãéêíóôõúç]+)*\b"
)
_PROPER_NOUN_TOKEN_PATTERN = re.compile(r"\b[A-ZÁÀÂÃÉÊÍÓÔÕÚÇ][a-záàâãéêíóôõúç]+\b|\b[A-Z]{2,6}\b")
_OFFICIAL_DOMAINS = (
    ".jus.br",
    ".gov.br",
    ".leg.br",
    "tse.jus.br",
    "stf.jus.br",
)

_FACTCHECK_DOMAINS = (
    "aosfatos.org",
    "lupa.uol.com.br",
    "fatoouboato",
    "checamos.afp.com",
    "uol.com.br/confere",
    "estadao.com.br/estadao-verifica",
    "projetocomprova.com.br",
)

_JOURNALISTIC_DOMAINS = (
    "g1.globo.com",
    "folha.uol.com.br",
    "estadao.com.br",
    "uol.com.br",
    "oglobo.globo.com",
    "bbc.com",
    "cnnbrasil.com.br",
    "poder360.com.br",
    "cartacapital.com.br",
    "jota.info",
    "valor.globo.com",
    "metropoles.com",
    "teletime.com.br",
    "reuters.com",
    "elpais.com",
    "platobr.com.br",
)

_CLICKBAIT_TERMS = {"BOMBÁSTICO", "URGENTE", "ATENÇÃO", "CORRE", "ALERTA"}


def _source_authority_score(evidence: Evidence) -> float:
    """Pontua a autoridade jornalística/institucional da evidência para priorização."""
    url = evidence.url.lower()
    for dom in _OFFICIAL_DOMAINS:
        if dom in url:
            return 3.0
    for dom in _FACTCHECK_DOMAINS:
        if dom in url:
            return 2.5
    for dom in _JOURNALISTIC_DOMAINS:
        if dom in url:
            return 2.0
    if evidence.source in ("google_factcheck", "rss_checkers"):
        return 2.5
    return 1.0


def _explicit_candidate_support(claim: str, evidences: list[Evidence]) -> str | None:
    """Detecta fonte que chama a pessoa da alegação de candidata ao Senado.

    É uma trava estreita de abstenção, não uma prova automática de verdade:
    evita que o Jev transforme uma lista parcial de debate em desmentido de
    candidatura quando a própria fonte nomeia a pessoa como candidata.
    """
    match = _CANDIDATE_CLAIM_PATTERN.search(claim)
    if not match:
        return None
    name = match.group("name").casefold()
    for evidence in evidences:
        text = f"{evidence.title} {evidence.snippet}".casefold()
        for occurrence in re.finditer(re.escape(name), text):
            surrounding = text[max(0, occurrence.start() - 120) : occurrence.end() + 180]
            if _SENATE_CANDIDATE_PATTERN.search(surrounding) and not _NEGATION_PATTERN.search(
                surrounding
            ):
                return evidence.url
    return None


def _url_key(url: str) -> str:
    """Mesma matéria com e sem www/https/barra final conta uma vez só."""
    key = re.sub(r"^https?://(www\.)?", "", url.strip().casefold())
    return key.rstrip("/")


def _word_overlap(claim: str, evidence: Evidence) -> int:
    claim_words = {word.casefold() for word in _WORD_PATTERN.findall(claim)}
    evidence_words = {
        word.casefold() for word in _WORD_PATTERN.findall(f"{evidence.title} {evidence.snippet}")
    }
    return len(claim_words & evidence_words)


def _has_direct_anchor_overlap(
    claim: str,
    evidence: Evidence,
    context_entity: str | None = None,
    author_handle: str | None = None,
) -> bool:
    """Exige âncoras e uma expressão factual compartilhada no título/trecho.

    Isto é um guardrail determinístico antes do classificador local. O Jev
    pode confundir uma coincidência geográfica ou temática com relevância; sem
    âncoras e uma expressão compartilhadas, uma fonte não pode confirmar nem
    desmentir o fato.
    """
    from app.clients.evidence.web_search import is_valid_evidence_url

    if not is_valid_evidence_url(evidence.url):
        return False

    if author_handle:
        author_clean = re.sub(
            r"\.(bsky\.social|com\.br|com|org)$", "", author_handle.strip().casefold()
        )
        if len(author_clean) >= 4:
            ev_text = f"{evidence.url} {evidence.title}".casefold()
            if author_clean in ev_text:
                return False

    claim_words = [word.casefold() for word in _WORD_PATTERN.findall(claim)]
    evidence_text = f"{evidence.title} {evidence.snippet}".casefold()
    evidence_words = [word.casefold() for word in _WORD_PATTERN.findall(evidence_text)]

    claim_informative = {w for w in claim_words if w not in _PORTUGUESE_STOPWORDS}
    evidence_informative = {w for w in evidence_words if w not in _PORTUGUESE_STOPWORDS}

    claim_numbers = set(re.findall(r"\b\d+(?:[.,]\d+)?\b", claim))
    evidence_numbers = set(re.findall(r"\b\d+(?:[.,]\d+)?\b", evidence_text))

    claim_entities = {
        w.casefold()
        for w in _PROPER_NOUN_TOKEN_PATTERN.findall(claim)
        if w.casefold() not in _PORTUGUESE_STOPWORDS and w.upper() not in _CLICKBAIT_TERMS
    }
    if context_entity:
        for w in _PROPER_NOUN_TOKEN_PATTERN.findall(context_entity):
            if w.casefold() not in _PORTUGUESE_STOPWORDS and w.upper() not in _CLICKBAIT_TERMS:
                claim_entities.add(w.casefold())

    if claim_entities and not (claim_entities & set(evidence_words)):
        return False
    if claim_numbers and not (claim_numbers & evidence_numbers):
        return False

    shared_informative = claim_informative & evidence_informative
    if len(shared_informative) < _MIN_DIRECT_ANCHOR_OVERLAP:
        return False

    # Guardrail de contexto: se o post trata de um caso ou entidade de contexto
    # específica (ex: "Ana Clara Gomes Machado") que difere da entidade da frase
    # ("Flávio Bolsonaro"), a evidência não pode coincidir apenas o político famoso.
    # Ela precisa compartilhar também a entidade de contexto OU termos do predicado/ação.
    if context_entity:
        context_tokens = {
            w.casefold()
            for w in _PROPER_NOUN_TOKEN_PATTERN.findall(context_entity)
            if w.casefold() not in _PORTUGUESE_STOPWORDS
        }
        claim_entity_tokens = {
            w.casefold()
            for w in _PROPER_NOUN_TOKEN_PATTERN.findall(claim)
            if w.casefold() not in _PORTUGUESE_STOPWORDS and w.upper() not in _CLICKBAIT_TERMS
        }
        predicate_informative = {w for w in claim_informative if w not in claim_entity_tokens}
        has_predicate_overlap = bool(evidence_informative & predicate_informative)
        has_context_overlap = bool(context_tokens & set(evidence_words))
        if not (has_predicate_overlap or has_context_overlap):
            return False

    # Guardrail de negação sobre terceiros (coreferência):
    # Se a matéria diz "Pessoa A diz que Pessoa B nunca...", a negação é sobre B.
    # Se a alegação trata de A e não de B, a evidência não contradiz A.
    denial_match = re.search(
        r"\b(?P<speaker>\w+(?:\s+\w+)?)\s+(?:diz|afirma|garante|disse|afirmou)\s+que\s+"
        r"(?:o\s+)?(?P<subject>\w+(?:\s+\w+)?)\s+(?:nunca|jamais)\b",
        f"{evidence.title} {evidence.snippet}",
        re.IGNORECASE,
    )
    if denial_match:
        speaker = denial_match.group("speaker").casefold()
        subject = denial_match.group("subject").casefold()
        sp_words = set(speaker.split())
        sub_words = set(subject.split())
        diff_sub = sub_words - sp_words
        if diff_sub:
            claim_lower = claim.casefold()
            if any(w in claim_lower for w in sp_words):
                claim_rest = claim_lower
                for w in sp_words:
                    claim_rest = re.sub(rf"\b{re.escape(w)}(?:\s+\w+)?\b", "", claim_rest)
                if not any(w in claim_rest for w in diff_sub):
                    return False

    claim_pairs = {
        (w1, w2)
        for w1, w2 in zip(claim_words, claim_words[1:], strict=False)
        if (w1 in claim_informative or w2 in claim_informative)
    }
    evidence_pairs = set(zip(evidence_words, evidence_words[1:], strict=False))
    return bool(claim_pairs & evidence_pairs)


_CAMPAIGN_SLOGAN_PATTERNS = [
    # Contagens regressivas eleitorais ("Faltam 7 dias para...")
    re.compile(r"\b(?:faltam|falta)\s+\d+\s+dias\b", re.IGNORECASE),
    # Chamadas diretas de voto ou número de urna ("Vote 13", "Confirme 22")
    re.compile(r"\b(?:vote|vota|votem|confirme)\s+\d{2}\b", re.IGNORECASE),
    # Torcida/slogan de eleição em primeiro/segundo turno sem contexto fático de eleição passada
    re.compile(
        r"\b(?:eleito|eleita|vit[oó]ria|venceremos)\s+no\s+(?:1[ºo]|primeiro|2[ºo]|segundo)\s+turno\b",
        re.IGNORECASE,
    ),
    # Aclamações majoritárias isoladas de campanha ("LULA PRESIDENTE", "BOLSONARO PRESIDENTE")
    re.compile(
        r"^(?:[a-záàâãéêíóôõúç]+\s+)?"
        r"(?:lula|bolsonaro|ciro|mar[çc]al|boulos|tarc[ií]sio|haddad)\s+"
        r"(?:presidente|governador|senador|prefeito)!?$",
        re.IGNORECASE,
    ),
    # Slogans comuns de torcida partidária
    re.compile(
        r"\b(?:rumo\s+[aà]\s+vit[oó]ria|[ée]\s+\d{2}\s+neles|[ée]\s+treze|[ée]\s+vinte\s+e\s+dois)\b",
        re.IGNORECASE,
    ),
    # Torcida / aclamações de campanha ("Bora Fulano", "Viva Fulano")
    re.compile(r"\b(?:bora|for[ac]|viva)\s+[A-ZÁÀÂÃÉÊÍÓÔÕÚÇ][a-záàâãéêíóôõúç]+\b", re.IGNORECASE),
    # Gírias e avaliações subjetivas de debate ("jantou", "amassou", "fugiu das perguntas")
    re.compile(
        r"\b(?:jantou|amassou|massacrou|humilhou|arrebentou|destruiu)\s+(?:o|a|os|as)?\s*\w+",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:fugiu|correu|arregou)\s+d[ao]s?\s+(?:perguntas?|debate)\b", re.IGNORECASE),
    re.compile(
        r"\b(?:venceu|perdeu|ganhou|foi\s+melhor\s+no|foi\s+pior\s+no)\s+o?\s*debate\b",
        re.IGNORECASE,
    ),
    # Orações relativas anafóricas sem sujeito explícito ("o mesmo que...", "aquele que...")
    re.compile(
        r"^(?:e\s+)?(?:o\s+mesmo|a\s+mesma|aquele|aquela)\s+que\b",
        re.IGNORECASE,
    ),
    # Blind items ou orações pronominais indeterminadas ("Só um recebeu...", "Apenas uma...")
    re.compile(
        r"^(?:s[oó]|apenas)\s+(?:um|uma)(?:\s+(?:candidat[oa]|pol[ií]tic[oa]))?\s+[a-záàâãéêíóôõúç]+",
        re.IGNORECASE,
    ),
    # Charadas políticas ou blind items sem candidato ("13 candidatos...", "tá fácil escolher")
    re.compile(r"^\d+\s+candidatos\b", re.IGNORECASE),
    re.compile(r"\bt[aá]\s+f[aá]cil\s+escolher\b", re.IGNORECASE),
]


def _is_campaign_label(fragment: str) -> bool:
    """Identificadores de comitê/núcleo e slogans de campanha/torcida eleitoral."""
    first_word = fragment.split(maxsplit=1)[0].casefold() if fragment.split() else ""
    if first_word in {"comitê", "comite", "núcleo", "nucleo"}:
        return True
    return any(pattern.search(fragment) for pattern in _CAMPAIGN_SLOGAN_PATTERNS)


def _extract_primary_entities(post_text: str) -> list[str]:
    """Extrai as entidades principais (pessoas, instituições, siglas) do post."""
    entities: list[str] = []
    # 1. Nomes em caixa alta (ex: FLÁVIO BOLSONARO)
    for match in _ALL_CAPS_NAME_PATTERN.finditer(post_text):
        cand = match.group(0)
        words = [
            w.capitalize()
            for w in cand.split()
            if w.casefold() not in _PORTUGUESE_STOPWORDS
            and w.casefold() not in _HEADLINE_TERMS
            and w.upper() not in _CLICKBAIT_TERMS
        ]
        if 2 <= len(words) <= 3:
            name = " ".join(words)
            if name not in entities:
                entities.append(name)

    # 2. Siglas em caixa alta (STF, TSE, PF, PL, PT, etc)
    for match in _ACRONYM_PATTERN.finditer(post_text):
        acronym = match.group(0)
        if (
            acronym not in _CLICKBAIT_TERMS
            and acronym.casefold() not in _PORTUGUESE_STOPWORDS
            and acronym.casefold() not in _HEADLINE_TERMS
            and len(acronym) >= 2
            and acronym not in entities
        ):
            entities.append(acronym)
    # 3. Nomes próprios (sequências capitalizadas)
    for match in _PROPER_NOUN_PATTERN.finditer(post_text):
        name = match.group(0).strip()
        first = name.split()[0].casefold()
        if (
            first not in _PORTUGUESE_STOPWORDS
            and name.upper() not in _CLICKBAIT_TERMS
            and len(name) >= 3
            and name not in entities
        ):
            entities.append(name)
    # Prioriza entidades compostas (ex: "Flávio Bolsonaro", "Luciano Huck")
    multi = [e for e in entities if len(e.split()) >= 2]
    return multi + [e for e in entities if e not in multi]


def _is_verifiable_claim(fragment: str) -> bool:
    """Filtra fragmentos que não constituem uma alegação factual verificável."""
    # Perguntas (retóricas ou diretas) não são asserções fáticas
    if fragment.endswith("?") or _QUESTION_PATTERN.match(fragment):
        return False
    # Expressões idiomáticas ou metafóricas isoladas ("a casa começou a cair", "caiu a ficha")
    if _IDIOM_PATTERNS.search(fragment):
        words = fragment.split()
        if len(words) <= 8 and not _METRIC_PATTERN.search(fragment):
            return False
    # Exige ao menos um ancoramento factual verificável:
    # 1. Métrica numérica, monetária, percentual ou ano
    if _METRIC_PATTERN.search(fragment):
        return True
    # 2. Título político ou institucional (ministro, senador, presidente, juiz, candidato)
    if _POLITICAL_TITLES_PATTERN.search(fragment):
        words = fragment.split()
        if (
            len(words) >= 8
            or _FACTUAL_PREDICATE_PATTERN.search(fragment)
            or re.search(
                r"\b(foi|é|era|será|disse|declarou|afirmou|votou|gastou|recebeu|perdeu|venceu|assumiu|quer|decretou)\b",
                fragment,
                re.IGNORECASE,
            )
        ):
            return True
        proper_nouns = _PROPER_NOUN_PATTERN.findall(fragment)
        first_word = words[0].rstrip(",.:;!?").casefold() if words else ""
        has_real_name = any(
            p.casefold() != first_word
            and p.upper() not in _CLICKBAIT_TERMS
            and p.casefold() not in _PORTUGUESE_STOPWORDS
            and p.upper() not in _UFS
            for p in proper_nouns
        )
        if has_real_name:
            return True
        return False
    # 3. Predicado fático, judicial ou investigativo específico
    if _FACTUAL_PREDICATE_PATTERN.search(fragment):
        return True
    # 4. Sigla institucional (STF, TSE, PF, CPMI, etc) -- UFs isoladas não contam
    acronyms = [
        a for a in _ACRONYM_PATTERN.findall(fragment) if a not in _CLICKBAIT_TERMS and a not in _UFS
    ]
    if acronyms:
        return True
    # 5. Entidade nomeada ou nome próprio além da primeira palavra capitalizada
    proper_nouns = _PROPER_NOUN_PATTERN.findall(fragment)
    first_word = fragment.split()[0].rstrip(",.:;!?").casefold() if fragment.split() else ""
    meaningful = [
        p
        for p in proper_nouns
        if p.casefold() != first_word
        and p.upper() not in _CLICKBAIT_TERMS
        and p.casefold() not in _PORTUGUESE_STOPWORDS
    ]
    if meaningful:
        return True
    return False


def jev_model_key(settings: Settings) -> str:
    """Chave de calibração CRC própria do backend Jev (não mistura com a chave do LLM)."""
    if settings.jev_model_file:
        return f"jev:{settings.jev_model_repo}:{settings.jev_model_file}"
    return f"jev:{settings.jev_model_repo}"


async def _fetch_article_text(url: str) -> str | None:
    return await fetch_article_text(url, max_chars=_ARTICLE_MAX_CHARS)


def _clean_query(text: str) -> str:
    """Remove URLs, conectivos suspensos ao final e normaliza espaços."""
    without_urls = _URL_PATTERN.sub("", text)
    cleaned = " ".join(without_urls.split())
    while True:
        stripped = _TRAILING_CONNECTOR_PATTERN.sub("", cleaned).strip()
        if stripped == cleaned:
            break
        cleaned = stripped
    return cleaned


_UFS = frozenset(
    "AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split()
)

_STATE_NAME_TO_UF = {
    "acre": "AC",
    "alagoas": "AL",
    "amapa": "AP",
    "amapá": "AP",
    "amazonas": "AM",
    "bahia": "BA",
    "ceara": "CE",
    "ceará": "CE",
    "distrito federal": "DF",
    "espirito santo": "ES",
    "espírito santo": "ES",
    "goias": "GO",
    "goiás": "GO",
    "maranhao": "MA",
    "maranhão": "MA",
    "mato grosso do sul": "MS",
    "mato grosso": "MT",
    "minas gerais": "MG",
    "para": "PA",
    "pará": "PA",
    "paraiba": "PB",
    "paraíba": "PB",
    "parana": "PR",
    "paraná": "PR",
    "pernambuco": "PE",
    "piaui": "PI",
    "piauí": "PI",
    "rio de janeiro": "RJ",
    "rio grande do norte": "RN",
    "rio grande do sul": "RS",
    "rondonia": "RO",
    "rondônia": "RO",
    "roraima": "RR",
    "santa catarina": "SC",
    "sao paulo": "SP",
    "são paulo": "SP",
    "sergipe": "SE",
    "tocantins": "TO",
}

_UF_PATTERN = re.compile(
    r"\b(?:d[oe]|em|no|na|pelo|pela|para|do estado d[oe])\s+([A-Z]{2})\b",
    re.IGNORECASE,
)


def _normalize_place(name: str) -> str:
    decomposed = unicodedata.normalize("NFKD", name.casefold())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).strip()


def _extract_ufs(text: str) -> set[str]:
    """Extrai siglas de UF ou nomes de estados brasileiros citados no texto."""
    ufs = set()
    norm = _normalize_place(text)
    for state_name, uf in _STATE_NAME_TO_UF.items():
        if re.search(rf"\b{re.escape(_normalize_place(state_name))}\b", norm):
            ufs.add(uf)
    for match in _UF_PATTERN.finditer(text):
        uf_cand = match.group(1).upper()
        if uf_cand in _UFS:
            ufs.add(uf_cand)
    for place_tuple in geo.places(text):
        if len(place_tuple) == 2 and place_tuple[1] in _UFS:
            ufs.add(place_tuple[1])
    return ufs


def _entity_conflict(claim: str, evidence: Evidence, discourse: str = "") -> str | None:
    """Detecta evidência sobre outra entidade homônima (outra localidade, UF ou zona eleitoral).

    O contexto é o post inteiro (`discourse`), não só o fragmento verificado: se o divisor perder
    a cidade ao cortar a frase, ela continua valendo. Só conclui conflito quando os dois lados
    citam o dado e não há nada em comum (ver `geo.places_conflict`); evidência sem localidade
    nem zona é neutra.
    """
    context = f"{claim} {discourse}".strip()
    text = f"{evidence.title} {evidence.snippet}"
    claim_zones, evidence_zones = geo.zones(context), geo.zones(text)
    if claim_zones and evidence_zones and claim_zones.isdisjoint(evidence_zones):
        return f"zona eleitoral diferente ({sorted(evidence_zones)} x {sorted(claim_zones)})"

    context_places, evidence_places = geo.places(context), geo.places(text)
    if geo.places_conflict(context_places, evidence_places):
        return f"localidade diferente ({sorted(evidence_places)} x {sorted(context_places)})"

    claim_ufs = _extract_ufs(context)
    evidence_ufs = _extract_ufs(text)
    if claim_ufs and evidence_ufs and claim_ufs.isdisjoint(evidence_ufs):
        return f"UF diferente ({sorted(evidence_ufs)} x {sorted(claim_ufs)})"
    return None


def _nli_chunks(title: str, text: str) -> list[str]:
    """Premissas para o NLI: o título e janelas de duas frases da matéria.

    O NLI foi treinado em pares de frases; documento inteiro contra uma frase dilui o sinal.
    Seguimos
    SummaC/AlignScore: segmentar o documento, pontuar cada trecho contra a alegação e ficar com o
    máximo.
    """
    sentences = [s for s in split_sentences(text) if len(s) > 20]
    windows = [" ".join(sentences[i : i + 2]) for i in range(0, len(sentences), 2)]
    chunks = [title] if title else []
    chunks += [w[:_CHUNK_MAX_CHARS] for w in windows[:_MAX_NLI_CHUNKS]]
    return chunks


def _title_from_url(url: str) -> str:
    """Título aproximado pela URL: portais de notícia põem o título da matéria no slug."""
    slug = urlparse(url).path.rstrip("/").rsplit("/", 1)[-1]
    slug = re.sub(r"\.(ghtml|html?|php|aspx?)$", "", slug)
    title = slug.replace("-", " ").replace("_", " ").strip()
    return title if len(title) >= 20 else ""


def _candidate_sentences(post_text: str) -> list[str]:
    """Quebra o post em frases candidatas (linha e depois ponto-final).

    Puramente determinístico (sem LLM nem Jev) -- o objetivo é só dar ao
    classificador pedaços pequenos o bastante pra não perder um número ou
    fato específico embutido em várias linhas de opinião/retórica.
    """
    fragments: list[str] = []
    for line in post_text.splitlines():
        line = line.strip()
        # Hashtags isoladas expressam campanha/posição, não uma alegação a
        # ser verificada. Antes elas chegavam ao Jev como uma frase factual.
        if not line or line.startswith("#"):
            continue
        # Remove prefixos de thread comuns que quebram o parser
        line = re.sub(r"^continua[çc][ãa]o\s+do\s+autor:\s*", "", line, flags=re.IGNORECASE)
        fragments.extend(part.strip() for part in split_sentences(line))

    seen: set[str] = set()
    candidates: list[str] = []
    for fragment in fragments:
        cleaned = _clean_query(fragment)
        if (
            len(cleaned) < _MIN_SENTENCE_LEN
            or cleaned in seen
            or _is_campaign_label(cleaned)
            or not _is_verifiable_claim(cleaned)
        ):
            continue
        seen.add(cleaned)
        candidates.append(cleaned)
        if len(candidates) >= _MAX_CANDIDATE_CLAIMS:
            break
    return candidates


@dataclass
class CitedSource:
    """Matéria linkada pelo post: a evidência (para o conjunto) e o texto completo (para o NLI)."""

    evidence: Evidence
    text: str


class JevVerificationService:
    """Verifica um post usando só classificação local (sem gerar JSON)."""

    def __init__(
        self,
        classifier: JevClassifierPort,
        sources: list[EvidenceSource],
        calibration_repo: CRCCalibrationRepository,
        *,
        settings: Settings | None = None,
    ) -> None:
        self.classifier = classifier
        self.sources = sources
        self.calibration_repo = calibration_repo
        self.settings = settings or get_settings()

    @classmethod
    def from_settings(
        cls,
        settings: Settings | None = None,
        engine=None,
    ) -> "JevVerificationService":
        resolved = settings or get_settings()
        resolved_engine = engine or create_engine(resolved.database_url)
        sources: list[EvidenceSource] = []
        for name in resolved.self_rag_enabled_sources:
            if name == GoogleFactCheckClient.name:
                source = GoogleFactCheckClient(api_key=resolved.google_factcheck_api_key)
            else:
                source = get_evidence_source(name, settings=resolved)
            sources.append(source)
        return cls(
            get_jev_classifier(resolved),
            sources,
            CRCCalibrationRepository(resolved_engine),
            settings=resolved,
        )

    def model_key(self) -> str:
        return jev_model_key(self.settings)

    async def verify(
        self,
        post: Post,
        *,
        quoted_text: str | None = None,
        parent_text: str | None = None,
        current_date: date | None = None,
    ) -> Verdict:
        agent_outputs: dict[str, str] = {}
        context_text = f"{post.text}\n{parent_text}" if parent_text else post.text
        # As alegações a serem verificadas e atribuídas ao autor no Bluesky DEVEM
        # vir exclusivamente do post atual (post.text) ou de continuações do mesmo autor.
        # 'Post anterior' (ancestrais/comentados) serve apenas como contexto temático
        # para desambiguação de entidades (ex: "ele", "o debate").
        # Nunca atribuir uma frase dita pelo post-pai ao autor do post-filho.
        claim_text_source = post.text
        if parent_text and "continuação do autor:" in parent_text:
            author_continuations = [
                part.split("post anterior:")[0].strip()
                for part in parent_text.split("continuação do autor:")[1:]
            ]
            claim_text_source = f"{post.text}\n" + "\n".join(author_continuations)
        candidates = _candidate_sentences(claim_text_source)
        if parent_text:
            agent_outputs["jev.thread_context"] = parent_text

        if not candidates:
            return Verdict(
                claim=post.text,
                label=VerdictLabel.INSUFFICIENT_EVIDENCE,
                confidence=0.0,
                rationale="Nenhuma alegação factual verificável identificada (classificado "
                "localmente).",
                agent_outputs=agent_outputs,
            )

        primary_entities = _extract_primary_entities(context_text)
        primary_entity = primary_entities[0] if primary_entities else None

        classification_log = []
        factual_claims: list[str] = []
        for sentence in candidates:
            judgment = await self.classifier.classify(
                f'Frase: "{sentence}"\n'
                "Essa frase é uma alegação factual verificável -- descreve um fato, "
                "número, evento ou declaração que pode ser checado contra a "
                "realidade -- ou é só opinião, desabafo, pergunta ou retórica?",
                ["factual", "opiniao"],
            )
            classification_log.append({"text": sentence, **judgment})
            if judgment["factual"] > judgment["opiniao"]:
                factual_claims.append(sentence)
        agent_outputs["jev.claim_classification"] = json.dumps(
            classification_log, ensure_ascii=False
        )

        if not factual_claims:
            return Verdict(
                claim=post.text,
                label=VerdictLabel.INSUFFICIENT_EVIDENCE,
                confidence=0.0,
                rationale="Nenhuma alegação factual verificável identificada (classificado "
                "localmente).",
                agent_outputs=agent_outputs,
            )

        cited = await self._cited_evidence(post)
        if cited:
            agent_outputs["jev.cited_links"] = json.dumps([c.evidence.url for c in cited])

        best: Verdict | None = None
        for index, claim in enumerate(factual_claims, start=1):
            candidate_verdict = await self._verify_claim(
                claim,
                agent_outputs,
                prefix=f"jev.c{index:02d}",
                post_date=post.created_at.date(),
                context_entity=primary_entity,
                author_handle=post.author_handle,
                cited=cited,
                discourse=context_text,
            )
            if candidate_verdict.label in (VerdictLabel.FALSE, VerdictLabel.MISLEADING):
                return candidate_verdict  # já passou pela calibração -- pode agir
            if best is None or candidate_verdict.confidence > best.confidence:
                best = candidate_verdict

        return best or Verdict(
            claim=post.text,
            label=VerdictLabel.INSUFFICIENT_EVIDENCE,
            confidence=0.0,
            rationale="Nenhuma alegação pôde ser verificada.",
            agent_outputs=agent_outputs,
        )

    async def _verify_claim(
        self,
        claim: str,
        agent_outputs: dict[str, str],
        *,
        prefix: str,
        post_date: date,
        context_entity: str | None = None,
        author_handle: str | None = None,
        cited: "list[CitedSource] | None" = None,
        discourse: str = "",
    ) -> Verdict:
        if cited:
            supported = await self._cited_support(claim, cited, discourse, agent_outputs, prefix)
            if supported is not None:
                source, entailment = supported
                return Verdict(
                    claim=claim,
                    label=VerdictLabel.SOURCE_CONSISTENT,
                    confidence=entailment,
                    rationale="O post é consistente com a matéria que ele próprio cita (a "
                    "veracidade da matéria não foi avaliada).",
                    evidences=[source.evidence],
                    agent_outputs=agent_outputs,
                )
        evidences, source_errors, query = await self._search(
            claim, post_date=post_date, context_entity=context_entity
        )
        if cited:
            # Fonte citada que não bastou para encerrar entra no conjunto: pode mostrar o post fora
            # de contexto, ou ser a única fonte sobre um fato muito recente.
            known = {_url_key(c.evidence.url) for c in cited}
            evidences = [
                *(c.evidence for c in cited),
                *(e for e in evidences if _url_key(e.url) not in known),
            ]
        agent_outputs[f"{prefix}.search_query"] = query
        agent_outputs[f"{prefix}.evidence_count"] = str(len(evidences))
        if source_errors:
            agent_outputs[f"{prefix}.source_errors"] = json.dumps(source_errors, ensure_ascii=False)
        if not evidences:
            return Verdict(
                claim=claim,
                label=VerdictLabel.INSUFFICIENT_EVIDENCE,
                confidence=0.0,
                rationale="Nenhuma fonte de evidência retornou resultado.",
                agent_outputs=agent_outputs,
            )

        relevant, relevance_log = await self._filter_relevant(
            claim,
            evidences,
            post_date=post_date,
            context_entity=context_entity,
            author_handle=author_handle,
            discourse=discourse,
        )
        agent_outputs[f"{prefix}.relevance"] = json.dumps(relevance_log, ensure_ascii=False)
        if not relevant:
            return Verdict(
                claim=claim,
                label=VerdictLabel.INSUFFICIENT_EVIDENCE,
                confidence=0.0,
                rationale="Nenhuma evidência relevante encontrada (classificado localmente).",
                agent_outputs=agent_outputs,
                evidences=evidences,
            )

        label, confidence, verdict_probs = await self._classify_verdict(
            claim, relevant, post_date=post_date
        )
        agent_outputs[f"{prefix}.verdict"] = json.dumps(verdict_probs, ensure_ascii=False)

        if label in (VerdictLabel.FALSE, VerdictLabel.MISLEADING):
            supporting_url = _explicit_candidate_support(claim, relevant)
            if supporting_url:
                agent_outputs[f"{prefix}.explicit_support_url"] = supporting_url
                return Verdict(
                    claim=claim,
                    label=VerdictLabel.INSUFFICIENT_EVIDENCE,
                    confidence=0.0,
                    rationale="Abstenção (Jev): fonte relevante apresenta a pessoa como "
                    "candidata ao Senado; veredito adverso contradiz a evidência.",
                    evidences=relevant,
                    agent_outputs=agent_outputs,
                )

        label, confidence, rationale = self._apply_calibration(label, confidence, len(relevant))
        return Verdict(
            claim=claim,
            label=label,
            confidence=confidence,
            rationale=rationale,
            evidences=relevant,
            agent_outputs=agent_outputs,
        )

    async def _cited_evidence(self, post: Post) -> "list[CitedSource]":
        """Lê as matérias linkadas pelo post (card de link, facets ou texto)."""
        sources: list[CitedSource] = []
        for url in post.links:
            if len(sources) >= _MAX_CITED_LINKS:
                break
            if not is_valid_evidence_url(url):  # rede social e UGC não são fonte
                continue
            text = await _fetch_article_text(url)
            if not text:
                continue
            title = _title_from_url(url) or text[:100]
            evidence = Evidence(
                source="post_link", url=url, title=title, snippet=text[:_SNIPPET_MAX_CHARS]
            )
            sources.append(CitedSource(evidence=evidence, text=text))
        return sources

    async def _cited_support(
        self,
        claim: str,
        cited: "list[CitedSource]",
        discourse: str,
        agent_outputs: dict[str, str],
        prefix: str,
    ) -> "tuple[CitedSource, float] | None":
        """A matéria citada sustenta a alegação? (NLI por trechos, máximo de entailment.)

        Só encerra a verificação quando a matéria é de fonte reconhecida (jornalística, checagem ou
        oficial): um post que repete um blog duvidoso continua sendo verificado, com a matéria
        entrando como mais uma evidência. O limiar vem de `app/scripts/eval_cited_support.py`.
        """
        best: tuple[CitedSource, float] | None = None
        for source in cited:
            if _entity_conflict(claim, source.evidence, discourse):
                continue
            chunks = _nli_chunks(source.evidence.title, source.text)
            if not chunks:
                continue
            results = await self.classifier.predict_nli_batch([(c, claim) for c in chunks])
            entailment = max(r["entailment"] for r in results)
            agent_outputs[f"{prefix}.cited_entailment"] = f"{source.evidence.url}: {entailment:.3f}"
            if best is None or entailment > best[1]:
                best = (source, entailment)
        if best is None or best[1] < self.settings.cited_source_entailment_min:
            return None
        if _source_authority_score(best[0].evidence) < self.settings.cited_source_min_authority:
            agent_outputs[f"{prefix}.cited_support_ignored"] = "fonte sem autoridade reconhecida"
            return None
        return best

    async def _filter_relevant(
        self,
        claim: str,
        evidences: list[Evidence],
        *,
        post_date: date | None = None,
        context_entity: str | None = None,
        author_handle: str | None = None,
        discourse: str = "",
    ) -> tuple[list[Evidence], list[dict]]:
        # Pré-filtro determinístico: sem duas âncoras específicas em comum, a
        # fonte não fala do fato. Isso impede que o modelo trate, por exemplo,
        # uma matéria qualquer sobre "Barcelona" como evidência sobre um bloco
        # político específico na cidade.
        log: list[dict] = []
        anchored: list[Evidence] = []
        for evidence in evidences:
            overlap = _word_overlap(claim, evidence)
            conflict = _entity_conflict(claim, evidence, discourse)
            if conflict:
                log.append(
                    {
                        "url": evidence.url,
                        "relevante": 0.0,
                        "irrelevante": 1.0,
                        "anchor_overlap": overlap,
                        "reason": f"entidade diferente: {conflict}",
                    }
                )
                continue
            if not _has_direct_anchor_overlap(
                claim, evidence, context_entity=context_entity, author_handle=author_handle
            ):
                # Alegações amplas (ex.: "a eleição foi fraudada") raramente
                # aparecem literalmente em uma única matéria. Se a fonte é
                # jornalística/oficial e há várias palavras informativas em
                # comum, deixe o classificador avaliar se ela confirma ou
                # desmente a alegação, em vez de abortar prematuramente.
                soft_overlap = _word_overlap(claim, evidence)
                soft_authority = _source_authority_score(evidence)
                if soft_overlap >= 2 and soft_authority >= 0.35:
                    anchored.append(evidence)
                    log.append(
                        {
                            "url": evidence.url,
                            "relevante": 0.5,
                            "irrelevante": 0.5,
                            "anchor_overlap": soft_overlap,
                            "reason": (
                                "encaminhada ao classificador por sobreposição temática "
                                "+ fonte confiável"
                            ),
                        }
                    )
                    continue
                log.append(
                    {
                        "url": evidence.url,
                        "relevante": 0.0,
                        "irrelevante": 1.0,
                        "anchor_overlap": overlap,
                        "reason": "âncoras ou expressão factual insuficientes",
                    }
                )
                continue
            anchored.append(evidence)

        # Prioriza fontes que tratam do fato específico da alegação (maior sobreposição lexical)
        # ponderado pela autoridade da fonte jornalística/oficial.
        shortlist = sorted(
            anchored,
            key=lambda item: (
                _word_overlap(claim, item) + _source_authority_score(item) * 2.0,
                _source_authority_score(item),
            ),
            reverse=True,
        )[:_MAX_EVIDENCE_FOR_RELEVANCE]
        scored: list[tuple[float, Evidence]] = []
        for evidence in shortlist:
            snippet = f"{evidence.title}. {evidence.snippet}"[:800]
            judgment = await self.classifier.classify(
                f'Alegação a verificar: "{claim}"\nTrecho de fonte: "{snippet}"\n'
                "O trecho cita os MESMOS fatos, pessoas, números ou eventos específicos "
                "da alegação (não conta só por ser sobre o mesmo tema genérico, como "
                'eleições ou política em geral)? Responda "relevante" só se o trecho '
                "realmente ajuda a confirmar ou refutar essa alegação específica."
                + (
                    f" A postagem é de {post_date:%d/%m/%Y}; se a alegação diz 'hoje', "
                    "'ontem' ou algo equivalente, a fonte precisa sustentar ou contradizer "
                    "o evento naquela data, não apenas citar o mesmo lugar."
                    if post_date and _TEMPORAL_REFERENCE_PATTERN.search(claim)
                    else ""
                ),
                ["relevante", "irrelevante"],
            )
            log.append(
                {
                    "url": evidence.url,
                    "anchor_overlap": _word_overlap(claim, evidence),
                    **judgment,
                }
            )
            margin = judgment["relevante"] - judgment["irrelevante"]
            if margin >= _RELEVANCE_MARGIN:
                scored.append((margin, evidence))
        scored.sort(
            key=lambda pair: (
                pair[0]
                + min(_word_overlap(claim, pair[1]), 12) * 0.08
                + _source_authority_score(pair[1]) * 0.15
            ),
            reverse=True,
        )
        return [evidence for _, evidence in scored], log

    async def _classify_verdict(
        self, claim: str, relevant: list[Evidence], *, post_date: date | None = None
    ) -> tuple[VerdictLabel, float, dict[str, float]]:
        candidates = relevant[:_MAX_EVIDENCE_FOR_VERDICT]
        articles = await asyncio.gather(*(_fetch_article_text(item.url) for item in candidates))
        temporal_context = (
            f" A postagem foi publicada em {post_date:%d/%m/%Y}."
            if post_date and _TEMPORAL_REFERENCE_PATTERN.search(claim)
            else ""
        )
        head = f'Alegação: "{claim}"{temporal_context}\nEvidências encontradas:\n'
        tail = "O que as evidências acima dizem sobre a alegação?"
        evidence_summary = await self._pack_evidence(head + tail, candidates, articles)
        options = list(_LABEL_BY_OPTION)
        probs = await self.classifier.classify(
            f"{head}{evidence_summary}{tail}",
            options,
        )
        best_option = max(probs, key=probs.get)
        return _LABEL_BY_OPTION[best_option], probs[best_option], probs

    async def _pack_evidence(
        self, fixed_text: str, candidates: list[Evidence], articles: list[str | None]
    ) -> str:
        """Blocos de evidência em ordem de relevância até o limite de contexto do Jev."""
        full_blocks = [
            f"- {item.title}: {article}\n" if article else None
            for item, article in zip(candidates, articles, strict=True)
        ]
        short_blocks = [
            f"- {item.title}: {item.snippet[:_SNIPPET_MAX_CHARS]}\n" for item in candidates
        ]
        texts = [fixed_text, *short_blocks, *(block for block in full_blocks if block)]
        counts = dict(zip(texts, await self.classifier.count_tokens(texts), strict=True))

        budget = self.settings.jev_n_ctx - PROMPT_OVERHEAD_TOKENS - counts[fixed_text]
        packed: list[str] = []
        for full, short in zip(full_blocks, short_blocks, strict=True):
            block = full if full and counts[full] <= budget else short
            if counts[block] > budget:
                continue
            packed.append(block)
            budget -= counts[block]
        return "".join(packed)

    def _apply_calibration(
        self, label: VerdictLabel, confidence: float, evidence_count: int
    ) -> tuple[VerdictLabel, float, str]:
        calibration = self.calibration_repo.get_latest(self.model_key())
        reasons: list[str] = []
        uncalibrated = calibration is None and self.settings.jev_allow_uncalibrated
        if calibration is None and not uncalibrated:
            reasons.append("não há calibração CRC para o modelo Jev")
        elif calibration is not None and confidence < calibration.lambda_hat:
            reasons.append("confiança abaixo de lambda_hat (Jev)")

        if reasons:
            return (
                VerdictLabel.INSUFFICIENT_EVIDENCE,
                0.0,
                f"Abstenção (Jev): {', '.join(reasons)}.",
            )
        rationale = (
            f"Classificado localmente (Jev) como '{label.value}' com confiança "
            f"{confidence:.0%}, com base em {evidence_count} evidência(s) relevante(s)."
        )
        if uncalibrated:
            rationale += " Sem calibração CRC (JEV_ALLOW_UNCALIBRATED)."
        return label, confidence, rationale

    async def _search(
        self,
        query: str,
        *,
        post_date: date | None = None,
        context_entity: str | None = None,
    ) -> tuple[list[Evidence], dict[str, str], str]:
        clean_query = _clean_query(query)
        search_query = clean_query
        queries = [search_query]

        # Consultas curtas recuperam checagens que não repetem a frase inteira
        # do post. Mantemos a consulta original e adicionamos combinações de
        # termos informativos para alegações compostas/retóricas.
        words = [
            w for w in _WORD_PATTERN.findall(clean_query)
            if w.casefold() not in _PORTUGUESE_STOPWORDS
        ]
        broad_claim_terms = {
            "eleição", "eleicoes", "eleições", "fraude", "fraudada", "fraudado", "urna", "voto"
        }
        if len(words) >= 12 and any(w.casefold() in broad_claim_terms for w in words):
            compact = " ".join(words[:10])
            if compact not in queries:
                queries.append(compact)
            anchors = [w for w in words if len(w) >= 6][:4]
            if len(anchors) >= 2:
                queries.append(" ".join(anchors[:2]))

        # Se a frase for uma anáfora ou omitir o sujeito principal do post,
        # injeta a entidade principal na query de busca externa.
        if context_entity and context_entity.casefold() not in clean_query.casefold():
            search_query = f"{clean_query} {context_entity}"
            queries = [search_query]
            claim_entities = [
                e for e in _extract_primary_entities(clean_query) if len(e.split()) >= 2
            ]
            if claim_entities:
                queries.append(f'"{context_entity}" "{claim_entities[0]}"')

        # Acrescenta a data somente para referências temporais explícitas.
        if post_date and _TEMPORAL_REFERENCE_PATTERN.search(clean_query):
            search_query = f"{search_query} {post_date:%d/%m/%Y}"
            queries[0] = search_query

        async def search_one(source: EvidenceSource):
            try:
                all_found = []
                for q in queries:
                    found = await asyncio.wait_for(
                        source.search(q, limit=3),
                        timeout=self.settings.evidence_timeout_seconds,
                    )
                    all_found.extend(found)
                    if len(all_found) >= 5:
                        break
                return source.name, all_found, None
            except Exception as exc:
                return source.name, [], type(exc).__name__

        results = await asyncio.gather(*(search_one(source) for source in self.sources))
        evidences: list[Evidence] = []
        errors: dict[str, str] = {}
        seen_urls: set[str] = set()
        for name, found, error in results:
            if error:
                errors[name] = error
                continue
            for item in found:
                key = _url_key(item.url)
                if key not in seen_urls:
                    seen_urls.add(key)
                    evidences.append(item)
        return evidences, errors, search_query
