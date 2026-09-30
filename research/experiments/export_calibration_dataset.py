"""Exporta decisões do banco (com rótulo humano) para o CSV de calibração CRC.

O objetivo é fazer o dataset de calibração
(`research/datasets/crc_calibration_predictions_ptbr.csv`) crescer com casos
reais coletados pelo pipeline em produção/showcase, sem depender só do
benchmark ClaimReview original. Rótulo (`expected_label`) nunca é inferido
automaticamente aqui -- vem de um arquivo `--labels` (JSON
`{"<post_uri>": "true|false|misleading", ...}`) preenchido por revisão
humana (ou por uma investigação de fact-check registrada à parte).

Nunca sobrescreve o CSV existente: linhas cujo `claim_id` já está presente
são puladas, e as demais são apenas anexadas ao final, preservando ordem e
conteúdo das linhas antigas.
"""

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

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

DEFAULT_CSV = REPOSITORY_ROOT / "research" / "datasets" / "crc_calibration_predictions_ptbr.csv"


def claim_id_for(post_uri: str) -> str:
    rkey = post_uri.rstrip("/").split("/")[-1]
    return f"bsky:{rkey}"


def sources_used(agent_outputs: dict[str, Any] | None) -> str:
    if not agent_outputs:
        return ""
    found: set[str] = set()
    for key, value in agent_outputs.items():
        if not key.endswith("[Sources]") or not isinstance(value, str):
            continue
        try:
            payload = json.loads(value)
        except json.JSONDecodeError:
            continue
        for item in payload.get("evidence", []):
            source = item.get("source")
            if source:
                found.add(source)
    return "+".join(sorted(found))


def error_flag(agent_outputs: dict[str, Any] | None) -> str:
    if not agent_outputs:
        return ""
    for key, value in agent_outputs.items():
        if key.endswith(".failure"):
            return str(value)
    return ""


def load_existing_claim_ids(csv_path: Path) -> set[str]:
    if not csv_path.exists():
        return set()
    with csv_path.open(encoding="utf-8", newline="") as handle:
        return {row["claim_id"] for row in csv.DictReader(handle)}


def latest_decision_per_post(session, post_uris: list[str]):
    from app.db.orm.decisions import DecisionLog

    latest: dict[str, DecisionLog] = {}
    rows = (
        session.query(DecisionLog)
        .filter(DecisionLog.post_uri.in_(post_uris))
        .order_by(DecisionLog.created_at.asc())
        .all()
    )
    for row in rows:
        latest[row.post_uri] = row  # a última sobrescreve: ordenado por created_at asc
    return latest


def build_rows(
    database_url: str,
    labels: dict[str, str],
    scenario: str,
    existing_claim_ids: set[str],
) -> tuple[list[dict[str, Any]], list[str]]:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    engine = create_engine(database_url)
    warnings: list[str] = []
    rows: list[dict[str, Any]] = []

    with Session(engine) as session:
        decisions_by_uri = latest_decision_per_post(session, list(labels.keys()))

        for post_uri, expected_label in labels.items():
            decision = decisions_by_uri.get(post_uri)
            if decision is None:
                warnings.append(f"Nenhuma decisão encontrada para {post_uri}; pulando.")
                continue

            claim_id = claim_id_for(post_uri)
            if claim_id in existing_claim_ids:
                warnings.append(f"{claim_id} já está no CSV; pulando (sem sobrescrever).")
                continue

            rows.append(
                {
                    "scenario": scenario,
                    "exclude_origin": False,
                    "sources": sources_used(decision.agent_outputs)
                    or "google_factcheck+wikipedia+web_search+rss_checkers",
                    "claim_id": claim_id,
                    "expected_label": expected_label,
                    "predicted_label": decision.verdict or "insufficient_evidence",
                    "confidence": decision.confidence if decision.confidence is not None else "",
                    "latency_seconds": "",
                    "cost_usd": "",
                    "evidence_count": len(decision.sources or []),
                    "error": error_flag(decision.agent_outputs),
                }
            )

    engine.dispose()
    return rows, warnings


def append_rows(csv_path: Path, rows: list[dict[str, Any]]) -> None:
    file_exists = csv_path.exists()
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        if not file_exists:
            writer.writeheader()
        for row in rows:
            writer.writerow(row)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--labels",
        type=Path,
        required=True,
        help="JSON {post_uri: expected_label} com rótulos revisados por humano",
    )
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--scenario", default="live_bsky_showcase")
    parser.add_argument("--dry-run", action="store_true", help="Não grava o CSV")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    labels = json.loads(args.labels.read_text(encoding="utf-8"))
    existing_claim_ids = load_existing_claim_ids(args.output)

    rows, warnings = build_rows(args.database_url, labels, args.scenario, existing_claim_ids)
    for warning in warnings:
        print(f"aviso: {warning}", file=sys.stderr)

    print(f"{len(rows)} nova(s) linha(s) para {args.output}")
    for row in rows:
        print(
            f"  + {row['claim_id']}: expected={row['expected_label']} "
            f"predicted={row['predicted_label']} confidence={row['confidence']}"
        )

    if not args.dry_run and rows:
        append_rows(args.output, rows)
        print(f"CSV atualizado (append-only): {args.output}")
    elif args.dry_run:
        print("dry-run: nada foi gravado")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
