"""Coletor de alegações checadas (ADR 0027).

O fluxo normal parte de posts políticos populares e procura checagem para eles; quase nunca
acha, porque quem repete uma alegação já desmentida costuma estar em respostas de threads, com
pouco engajamento. Aqui o caminho é o inverso: parte das checagens recentes de agências
(Google Fact Check e acervo RSS), busca no Bluesky os posts com os termos mais raros de cada
alegação e manda os que cobrem boa parte dela para a fila de intervenção, com a checagem como
fonte. Quem decide se o post repete mesmo a alegação é a revisão das fontes e o auditor
semântico da intervenção; aqui ficam só filtros baratos (desmentidos e cobertura mínima).

Os candidatos ficam num backlog e são liberados um por rodada de intervenção: a fila publica só
o melhor de cada rodada e descarta os demais, então mandar vários de uma vez desperdiçaria.
"""

import asyncio
import json
import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from app.clients.evidence.google_factcheck import GoogleFactCheckClient
from app.core.config import Settings
from app.domain.entities import Evidence, Post, Verdict, VerdictLabel
from app.domain.factcheck_claims import (
    RatingKind,
    checked_claim,
    informative_tokens,
    looks_like_debunk,
    publisher_name,
    rare_query_terms,
    weighted_coverage,
)

logger = logging.getLogger("contraria.claim_harvester")

_CORPUS_SIZE = 5000


@dataclass
class HarvestCandidate:
    post: Post
    evidence: Evidence
    checked: str
    kind: RatingKind
    coverage: float
    found_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class ClaimHarvester:
    def __init__(
        self,
        settings: Settings,
        bluesky,
        post_repo,
        pipeline,
        factcheck: GoogleFactCheckClient | None = None,
        fact_articles=None,
        classifier=None,
    ) -> None:
        self.settings = settings
        self.bluesky = bluesky
        self.post_repo = post_repo
        self.pipeline = pipeline
        self.factcheck = factcheck or GoogleFactCheckClient(
            max_age_days=settings.claim_harvest_max_age_days
        )
        self.fact_articles = fact_articles
        self.classifier = classifier
        self.backlog: list[HarvestCandidate] = []
        self._seen: set[str] = set()

    async def _checked_claims(self) -> list[tuple[Evidence, str, RatingKind]]:
        """Alegações falsas ou enganosas checadas recentemente, sem repetição."""
        evidences: list[Evidence] = []
        for query in self.settings.claim_harvest_queries:
            evidences.extend(await self.factcheck.search(query, limit=100))
        if self.fact_articles is not None:
            try:
                rows = self.fact_articles.recent_for_collection(
                    limit=200, max_age_days=self.settings.claim_harvest_max_age_days
                )
            except Exception as exc:
                logger.warning("Acervo RSS indisponível para o coletor: %s", type(exc).__name__)
                rows = []
            evidences.extend(
                Evidence(
                    source="rss_checkers",
                    url=row.get("url", ""),
                    title=row["title"],
                    snippet=row.get("summary") or "",
                )
                for row in rows
                if row.get("url")
            )
        claims: list[tuple[Evidence, str, RatingKind]] = []
        seen: set[str] = set()
        for evidence in evidences:
            found = checked_claim(evidence)
            if found is None or found[1] == RatingKind.TRUE:
                continue
            key = " ".join(informative_tokens(found[0]))
            if not key or key in seen:
                continue
            seen.add(key)
            claims.append((evidence, found[0], found[1]))
        return claims[: self.settings.claim_harvest_max_claims]

    def _document_frequency(self) -> tuple[Counter, int]:
        frequency: Counter = Counter()
        texts = self.post_repo.recent_texts(_CORPUS_SIZE)
        for text in texts:
            frequency.update(set(informative_tokens(text or "")))
        return frequency, len(texts)

    async def run(self) -> dict[str, int]:
        """Busca candidatos novos e os guarda no backlog (não analisa nada aqui)."""
        claims = await self._checked_claims()
        frequency, corpus_size = await asyncio.to_thread(self._document_frequency)
        since = datetime.now(UTC) - timedelta(hours=self.settings.claim_harvest_lookback_hours)
        best: dict[str, HarvestCandidate] = {}
        searched = 0
        for evidence, checked, kind in claims:
            terms = rare_query_terms(checked, frequency)
            if len(terms) < 2:
                continue
            searched += 1
            posts = []
            for sort in ("latest", "top"):
                try:
                    posts += await self.bluesky.search_posts(
                        query=" ".join(terms),
                        lang="pt",
                        sort=sort,
                        since=since,
                        limit=self.settings.claim_harvest_posts_per_claim,
                    )
                except Exception as exc:
                    logger.warning("searchPosts falhou no coletor (%s)", type(exc).__name__)
            per_claim: dict[str, HarvestCandidate] = {}
            for post in posts:
                if post.uri in self._seen or looks_like_debunk(post.text):
                    continue
                coverage = weighted_coverage(post.text, checked, frequency, corpus_size)
                if coverage < self.settings.claim_harvest_min_coverage:
                    continue
                per_claim[post.uri] = HarvestCandidate(post, evidence, checked, kind, coverage)
            top = sorted(per_claim.values(), key=lambda c: c.coverage, reverse=True)
            for candidate in await self._drop_contradictions(
                top[: self.settings.claim_harvest_max_per_claim]
            ):
                current = best.get(candidate.post.uri)
                if current is None or candidate.coverage > current.coverage:
                    best[candidate.post.uri] = candidate
        # Spam repetido (mesmo texto em vários posts) entra uma vez só.
        known_texts = {_text_key(c.post.text) for c in self.backlog}
        fresh: list[HarvestCandidate] = []
        for candidate in sorted(best.values(), key=lambda c: c.coverage, reverse=True):
            self._seen.add(candidate.post.uri)
            key = _text_key(candidate.post.text)
            if key in known_texts:
                continue
            known_texts.add(key)
            fresh.append(candidate)
        self.backlog.extend(fresh)
        self._expire()
        self.backlog.sort(key=lambda c: c.coverage, reverse=True)
        report = {
            "claims": len(claims),
            "searched": searched,
            "new_candidates": len(fresh),
            "backlog": len(self.backlog),
        }
        logger.info("Coletor de alegações checadas: %s", report)
        return report

    async def _drop_contradictions(
        self, candidates: list[HarvestCandidate]
    ) -> list[HarvestCandidate]:
        """Descarta posts que dizem o contrário da alegação falsa (NLI do Jev, local)."""
        if self.classifier is None or not candidates:
            return candidates
        try:
            results = await self.classifier.predict_nli_batch(
                [(c.post.text[:1200], c.checked[:400]) for c in candidates]
            )
        except Exception as exc:
            logger.warning("NLI indisponível no coletor (%s)", type(exc).__name__)
            return candidates
        limit = self.settings.claim_harvest_max_contradiction
        return [
            c
            for c, nli in zip(candidates, results, strict=True)
            if nli.get("contradiction", 0.0) < limit
        ]

    async def run_forever(self) -> None:
        """Coleta periódica fora do loop principal: são centenas de buscas por rodada."""
        while True:
            try:
                await self.run()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("Falha no coletor de alegações checadas (%s)", type(exc).__name__)
            await asyncio.sleep(self.settings.claim_harvest_minutes * 60)

    def _expire(self) -> None:
        cutoff = datetime.now(UTC) - timedelta(hours=self.settings.claim_harvest_backlog_hours)
        self.backlog = [c for c in self.backlog if c.found_at >= cutoff]

    async def release_one(self) -> bool:
        """Analisa o melhor candidato do backlog (ele entra na fila de intervenção)."""
        self._expire()
        if not self.backlog:
            return False
        candidate = self.backlog.pop(0)
        self.post_repo.upsert_posts(
            [
                {
                    "uri": candidate.post.uri,
                    "cid": candidate.post.cid,
                    "author_did": candidate.post.author_did,
                    "text": candidate.post.text,
                    "langs": candidate.post.langs,
                    "created_at": candidate.post.created_at,
                    "source": "claim_harvest",
                    "triage_status": "processed",
                    "priority": 0.0,
                }
            ]
        )
        await self.pipeline.analyze(candidate.post, verdict=_verdict(candidate))
        return True


def _text_key(text: str) -> str:
    return " ".join(informative_tokens(text))[:200]


def _verdict(candidate: HarvestCandidate) -> Verdict:
    label = VerdictLabel.FALSE if candidate.kind == RatingKind.FALSE else VerdictLabel.MISLEADING
    publisher = publisher_name(candidate.evidence)
    return Verdict(
        claim=candidate.post.text[:300],
        label=label,
        confidence=round(candidate.coverage, 3),
        rationale=(
            f"O post parece repetir alegação checada por {publisher} "
            f'({candidate.evidence.rating or candidate.kind.value}): "{candidate.checked}". '
            "A revisão das fontes confirma antes de publicar."
        ),
        evidences=[candidate.evidence],
        agent_outputs={
            "claim_harvest": json.dumps(
                {
                    "url": candidate.evidence.url,
                    "rating": candidate.evidence.rating,
                    "checked_claim": candidate.checked,
                    "coverage": round(candidate.coverage, 3),
                },
                ensure_ascii=False,
            )
        },
    )
