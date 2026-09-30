import asyncio
from datetime import datetime

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.orm.decisions import DecisionLog
from app.domain.entities import Evidence, Post, VerdictLabel
from app.services.jev_verification import (
    JevVerificationService,
    _candidate_sentences,
    _explicit_candidate_support,
)


async def replay_decision_historical(service: JevVerificationService, decision: DecisionLog):
    print(f"\n==================== REPLAY HISTÓRICO ID {decision.id} ====================")
    snapshot = decision.post_snapshot
    created_at = datetime.fromisoformat(snapshot["created_at"])
    post = Post(
        uri=decision.post_uri,
        cid=snapshot.get("cid", ""),
        author_did=snapshot.get("author_did", ""),
        text=snapshot["text"],
        created_at=created_at,
    )
    print(f"Texto do post: {post.text[:120]!r}")
    print(f"Decisão histórica original: veredito={decision.verdict} conf={decision.confidence}")

    raw_sources = decision.sources or []
    historical_evidences = [
        Evidence(
            source=s.get("source", "historical"),
            url=s["url"],
            title=s.get("title", ""),
            snippet=s.get("snippet", ""),
        )
        for s in raw_sources
    ]
    print(f"Fontes históricas salvas ({len(historical_evidences)}):")
    for s in historical_evidences:
        print(f"  - [{s.source}] {s.title[:60]!r} ({s.url})")

    candidates = _candidate_sentences(post.text)
    print(f"Candidatos a alegação ({len(candidates)}): {candidates}")

    for idx, claim in enumerate(candidates, 1):
        print(f"\n--- Analisando alegação {idx}: {claim!r} ---")
        relevant, rel_log = await service._filter_relevant(
            claim, historical_evidences, post_date=created_at.date()
        )
        print(f"  Evidências relevantes após filtro: {len(relevant)}")
        for r in relevant:
            print(f"    * {r.title[:60]!r} ({r.url})")

        if not relevant:
            print("  -> Nenhuma evidência relevante (insufficient_evidence)")
            continue

        raw_label, raw_conf, raw_probs = await service._classify_verdict(
            claim, relevant, post_date=created_at.date()
        )
        print(f"  Veredito bruto do Jev: label={raw_label} conf={raw_conf:.10f}")
        print(f"  Probabilidades brutas: {raw_probs}")

        if raw_label in (VerdictLabel.FALSE, VerdictLabel.MISLEADING):
            support_url = _explicit_candidate_support(claim, relevant)
            if support_url:
                print(f"  [TRAVA ATIVADA] Suporte explícito encontrado em: {support_url}")
                print("  -> Convertido em insufficient_evidence (confiança 0.0)")
                continue

        cal_label, cal_conf, rationale = service._apply_calibration(
            raw_label, raw_conf, len(relevant)
        )
        print(f"  Resultado após CRC: label={cal_label} conf={cal_conf:.10f} ({rationale})")


async def main():
    settings = get_settings()
    engine = create_engine(settings.database_url)
    service = JevVerificationService.from_settings(settings=settings, engine=engine)

    with Session(engine) as session:
        for did in [624, 493, 467]:
            decision = session.execute(
                select(DecisionLog).where(DecisionLog.id == did)
            ).scalar_one_or_none()
            if not decision:
                print(f"Decisão {did} não encontrada no banco.")
                continue
            await replay_decision_historical(service, decision)


if __name__ == "__main__":
    asyncio.run(main())
