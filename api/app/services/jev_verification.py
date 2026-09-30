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
from datetime import date

from sqlalchemy import create_engine

from app.clients.articles import fetch_article_text
from app.clients.evidence import get_evidence_source
from app.clients.evidence.base import EvidenceSource
from app.clients.evidence.google_factcheck import GoogleFactCheckClient
from app.core.config import Settings, get_settings
from app.domain.entities import Evidence, Post, Verdict, VerdictLabel
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
_SNIPPET_MAX_CHARS = 400
_WORD_PATTERN = re.compile(r"\w{4,}")
# Uma coincidência isolada (sobretudo cidade, país ou tema amplo) não mostra
# que a fonte trata da mesma alegação. Ex.: uma página que menciona Barcelona
# não é evidência sobre um evento específico ocorrido em Barcelona.
_MIN_DIRECT_ANCHOR_OVERLAP = 2
_TEMPORAL_REFERENCE_PATTERN = re.compile(
    r"\b(hoje|ontem|amanh[ãa]|agora|acaba de|esta semana|nesta semana|neste m[eê]s)\b",
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


def _has_direct_anchor_overlap(claim: str, evidence: Evidence) -> bool:
    """Exige âncoras e uma expressão factual compartilhada no título/trecho.

    Isto é um guardrail determinístico antes do classificador local. O Jev
    pode confundir uma coincidência geográfica ou temática com relevância; sem
    âncoras e uma expressão compartilhadas, uma fonte não pode confirmar nem
    desmentir o fato.
    """
    claim_words = [word.casefold() for word in _WORD_PATTERN.findall(claim)]
    evidence_words = [
        word.casefold() for word in _WORD_PATTERN.findall(f"{evidence.title} {evidence.snippet}")
    ]
    claim_pairs = set(zip(claim_words, claim_words[1:], strict=False))
    evidence_pairs = set(zip(evidence_words, evidence_words[1:], strict=False))
    return len(set(claim_words) & set(evidence_words)) >= _MIN_DIRECT_ANCHOR_OVERLAP and bool(
        claim_pairs & evidence_pairs
    )


def _is_campaign_label(fragment: str) -> bool:
    """Identificadores de comitê/núcleo não são alegações a contestar."""
    first_word = fragment.split(maxsplit=1)[0].casefold() if fragment.split() else ""
    return first_word in {"comitê", "comite", "núcleo", "nucleo"}


def jev_model_key(settings: Settings) -> str:
    """Chave de calibração CRC própria do backend Jev (não mistura com a chave do LLM)."""
    if settings.jev_model_file:
        return f"jev:{settings.jev_model_repo}:{settings.jev_model_file}"
    return f"jev:{settings.jev_model_repo}"


async def _fetch_article_text(url: str) -> str | None:
    return await fetch_article_text(url, max_chars=_ARTICLE_MAX_CHARS)


def _clean_query(text: str) -> str:
    """Remove URLs e normaliza espaços -- URL na query confundia a busca."""
    without_urls = _URL_PATTERN.sub("", text)
    return " ".join(without_urls.split())


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
        fragments.extend(part.strip() for part in re.split(r"(?<=[.!?])\s+", line))

    seen: set[str] = set()
    candidates: list[str] = []
    for fragment in fragments:
        cleaned = _clean_query(fragment)
        if len(cleaned) < _MIN_SENTENCE_LEN or cleaned in seen or _is_campaign_label(cleaned):
            continue
        seen.add(cleaned)
        candidates.append(cleaned)
        if len(candidates) >= _MAX_CANDIDATE_CLAIMS:
            break
    return candidates or [_clean_query(post_text)]


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
        candidates = _candidate_sentences(context_text)
        if parent_text:
            agent_outputs["jev.thread_context"] = parent_text

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

        best: Verdict | None = None
        for index, claim in enumerate(factual_claims, start=1):
            candidate_verdict = await self._verify_claim(
                claim,
                agent_outputs,
                prefix=f"jev.c{index:02d}",
                post_date=post.created_at.date(),
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
    ) -> Verdict:
        evidences, source_errors, query = await self._search(claim, post_date=post_date)
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

        relevant, relevance_log = await self._filter_relevant(claim, evidences, post_date=post_date)
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

    async def _filter_relevant(
        self, claim: str, evidences: list[Evidence], *, post_date: date | None = None
    ) -> tuple[list[Evidence], list[dict]]:
        # Pré-filtro determinístico: sem duas âncoras específicas em comum, a
        # fonte não fala do fato. Isso impede que o modelo trate, por exemplo,
        # uma matéria qualquer sobre "Barcelona" como evidência sobre um bloco
        # político específico na cidade.
        log: list[dict] = []
        anchored: list[Evidence] = []
        for evidence in evidences:
            overlap = _word_overlap(claim, evidence)
            if not _has_direct_anchor_overlap(claim, evidence):
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

        # Só as fontes ancoradas mais próximas chegam ao Jev para a segunda
        # checagem semântica de relevância.
        shortlist = sorted(anchored, key=lambda item: _word_overlap(claim, item), reverse=True)[
            :_MAX_EVIDENCE_FOR_RELEVANCE
        ]
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
        scored.sort(key=lambda pair: pair[0], reverse=True)
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
        self, query: str, *, post_date: date | None = None
    ) -> tuple[list[Evidence], dict[str, str], str]:
        clean_query = _clean_query(query)
        search_query = clean_query
        # Acrescenta a data somente para referências temporais explícitas. Não
        # impõe janela de recência: uma checagem posterior ainda pode refutar
        # corretamente um post antigo.
        if post_date and _TEMPORAL_REFERENCE_PATTERN.search(clean_query):
            search_query = f"{clean_query} {post_date:%d/%m/%Y}"

        async def search_one(source: EvidenceSource):
            try:
                found = await asyncio.wait_for(
                    source.search(search_query, limit=3),
                    timeout=self.settings.evidence_timeout_seconds,
                )
                return source.name, found, None
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
