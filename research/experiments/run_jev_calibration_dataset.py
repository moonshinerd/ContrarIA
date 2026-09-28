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
import traceback
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
        error = f"{type(exc).__name__}: {exc}"[:300]
        traceback.print_exc(file=sys.stderr)
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


class UngatedCalibrationRepository:
    """Calibração com lambda_hat=0: o Jev devolve o rótulo e a confiança crus.

    Com o repositório real, sem calibração do Jev no banco, todo veredito vira
    insufficient_evidence com confiança 0 -- o CSV registraria a ausência de
    calibração em vez da previsão, e o CRC calcularia o limiar sobre nada.
    """

    def get_latest(self, model: str):
        from app.services.crc import CRCCalibration

        return CRCCalibration(
            lambda_hat=0.0, alpha=1.0, n=0, model=model, created_at=datetime.now(UTC)
        )


_EARLY_CHECK = 3


def print_summary(output: Path) -> None:
    with output.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    errors = sum(1 for row in rows if row["error"])
    adverse = sum(1 for row in rows if row["predicted_label"] in ("false", "misleading"))
    print(
        f"\n{len(rows)} previsões em {output}: {errors} com erro, {adverse} adversas "
        "(false/misleading).",
        file=sys.stderr,
    )
    if errors or not adverse:
        print(
            "ATENÇÃO: calibração inválida. Com erros ou sem nenhuma previsão adversa o CRC "
            "devolve lambda_hat=0, que não trava nada. Não faça commit; veja o guia.",
            file=sys.stderr,
        )


def completed_claim_ids(output: Path) -> set[str]:
    if not output.exists():
        return set()
    with output.open(encoding="utf-8", newline="") as handle:
        return {row["claim_id"] for row in csv.DictReader(handle)}


async def main_async(args: argparse.Namespace) -> None:
    from app.core.config import get_settings
    from app.services.jev_verification import JevVerificationService

    settings = get_settings()
    service = JevVerificationService.from_settings(settings=settings)
    service.calibration_repo = UngatedCalibrationRepository()

    claims = load_claims(args.dataset)
    if args.limit:
        claims = claims[: args.limit]

    # Grava linha a linha e retoma de onde parou: cada claim leva até ~3 min.
    done = completed_claim_ids(args.output)
    processed: list[dict] = []
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        if not done:
            writer.writeheader()
        for index, claim_row in enumerate(claims, start=1):
            if str(claim_row["id"]) in done:
                continue
            print(f"[{index}/{len(claims)}] {claim_row['claim'][:70]!r}", file=sys.stderr)
            row = await run_one(service, claim_row)
            writer.writerow(row)
            handle.flush()
            print(
                f"  -> esperado={row['expected_label']} previsto={row['predicted_label']} "
                f"confiança={row['confidence']:.2f} ({row['latency_seconds']}s)"
                + (f" ERRO {row['error']}" if row["error"] else ""),
                file=sys.stderr,
            )
            processed.append(row)
            # Aborta cedo: se as primeiras falham, o resto também vai falhar e
            # a calibração sairia inútil (tudo insufficient_evidence).
            if len(processed) == _EARLY_CHECK and all(item["error"] for item in processed):
                raise SystemExit(
                    f"As {_EARLY_CHECK} primeiras alegações falharam; corrija o erro acima "
                    "antes de continuar."
                )
    print_summary(args.output)


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
