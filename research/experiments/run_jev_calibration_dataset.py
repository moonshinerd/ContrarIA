"""Roda o backend Jev contra o dataset real de calibração (ClaimReviews) e
grava as previsões num CSV compatível com calibrate_crc.py.

Diferente de research/experiments/calibrate_crc.py (que só calcula o limiar
a partir de um CSV já pronto), este script GERA esse CSV rodando o pipeline
Jev de verdade contra cada claim rotulada -- é o "pré-treino"/calibração do
Jev com dados que já sabemos ser reais ou falsos, sem depender do Ozone.

Uso (dentro do container, onde as dependências do app existem):
    python /research/experiments/run_jev_calibration_dataset.py \
        /research/datasets/crc_calibration_claimreviews_ptbr.jsonl \
        --output /research/datasets/crc_calibration_predictions_jev.csv
"""

import argparse
import asyncio
import csv
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
API_ROOT = REPOSITORY_ROOT / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

CSV_FIELDS = [
    "scenario",
    "exclude_origin",
    "sources",
    "claim_id",
    "expected_label",
    "predicted_label",
    "confidence",
    "latency_seconds",
    "cost_usd",
    "evidence_count",
    "error",
]


def load_claims(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


async def run_one(service, claim_row: dict) -> dict:
    from app.domain.entities import Post

    post = Post(
        uri=f"at://calibration/{claim_row['id']}",
        cid="calibration",
        author_did="did:calibration",
        text=claim_row["claim"],
        created_at=datetime.now(UTC),
    )
    t0 = asyncio.get_event_loop().time()
    error = ""
    try:
        verdict = await service.verify(post)
        predicted_label = verdict.label.value
        confidence = verdict.confidence
        evidence_count = len(verdict.evidences)
    except Exception as exc:  # nunca deve travar a calibração inteira
        predicted_label = "insufficient_evidence"
        confidence = 0.0
        evidence_count = 0
        error = type(exc).__name__
    latency = asyncio.get_event_loop().time() - t0

    return {
        "scenario": "jev_local_classifier",
        "exclude_origin": False,
        "sources": "+".join(service.settings.self_rag_enabled_sources),
        "claim_id": claim_row["id"],
        "expected_label": claim_row["label"],
        "predicted_label": predicted_label,
        "confidence": confidence,
        "latency_seconds": round(latency, 2),
        "cost_usd": 0.0,  # classificação local -- sem custo de API
        "evidence_count": evidence_count,
        "error": error,
    }


async def main_async(args: argparse.Namespace) -> None:
    from app.core.config import get_settings
    from app.services.jev_verification import JevVerificationService

    settings = get_settings()
    service = JevVerificationService.from_settings(settings=settings)

    claims = load_claims(args.dataset)
    if args.limit:
        claims = claims[: args.limit]

    rows = []
    for index, claim_row in enumerate(claims, start=1):
        print(f"[{index}/{len(claims)}] {claim_row['claim'][:70]!r}", file=sys.stderr)
        row = await run_one(service, claim_row)
        rows.append(row)
        print(f"  -> esperado={row['expected_label']} previsto={row['predicted_label']} "
              f"confiança={row['confidence']:.2f} ({row['latency_seconds']}s)", file=sys.stderr)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"\n{len(rows)} linha(s) gravada(s) em {args.output}", file=sys.stderr)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path, help="JSONL com claim/label (ClaimReviews)")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=None, help="Rodar só os N primeiros")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    asyncio.run(main_async(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
