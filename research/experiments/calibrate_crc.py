"""Calibra e persiste o limiar CRC a partir de predições rotuladas."""

import argparse
import csv
import importlib.util
import json
import os
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
API_ROOT = REPOSITORY_ROOT / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

CRC_MODULE_PATH = API_ROOT / "app" / "services" / "crc.py"
CRC_SPEC = importlib.util.spec_from_file_location("contraria_crc", CRC_MODULE_PATH)
if CRC_SPEC is None or CRC_SPEC.loader is None:
    raise RuntimeError(f"Não foi possível carregar {CRC_MODULE_PATH}")
CRC_MODULE = importlib.util.module_from_spec(CRC_SPEC)
sys.modules[CRC_SPEC.name] = CRC_MODULE
CRC_SPEC.loader.exec_module(CRC_MODULE)

CalibrationExample = CRC_MODULE.CalibrationExample
CalibrationResult = CRC_MODULE.CalibrationResult
CRCCalibration = CRC_MODULE.CRCCalibration
calibrate_threshold = CRC_MODULE.calibrate_threshold


def _normalized(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value).strip().casefold())
    return "".join(char for char in text if not unicodedata.combining(char))


def normalize_label(value: Any) -> str:
    """Mapeia textualRating em português e rótulos canônicos."""
    label = _normalized(value)
    if (
        label == "true" or any(term in label for term in ("verdadeir", "corret"))
    ) and "nao" not in label:
        return "true"
    if label == "misleading" or any(
        term in label for term in ("enganos", "imprecis", "sem contexto")
    ):
        return "misleading"
    if label == "false" or any(term in label for term in ("fals", "nao e verdade")):
        return "false"
    if label in {"insufficient_evidence", "inconclusivo", "inconclusiva"}:
        return "insufficient_evidence"
    if "nao" in label and "verdadeir" in label:
        return "false"
    raise ValueError(f"Rótulo não reconhecido: {value!r}")


def _read_rows(path: Path) -> list[dict[str, Any]]:
    if path.suffix.casefold() == ".csv":
        with path.open(encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))
    if path.suffix.casefold() == ".jsonl":
        with path.open(encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if isinstance(payload, dict):
        payload = payload.get("items", payload.get("examples"))
    if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
        raise ValueError("O dataset deve ser uma lista JSON ou CSV com cabeçalho")
    return payload


def _row_id(row: dict[str, Any], index: int) -> str:
    return str(row.get("id") or row.get("claim_id") or row.get("url") or f"row-{index}")


def load_examples(path: Path) -> list[CalibrationExample]:
    examples: list[CalibrationExample] = []
    for index, row in enumerate(_read_rows(path), start=1):
        actual = row.get(
            "actual_label",
            row.get("true_label", row.get("expected_label", row.get("textualRating"))),
        )
        predicted = row.get("predicted_label", row.get("prediction", row.get("verdict")))
        confidence = row.get("confidence")
        if actual is None or predicted is None or confidence is None:
            raise ValueError(
                f"Linha {index}: actual_label/expected_label/textualRating, predicted_label "
                "e confidence são obrigatórios"
            )
        examples.append(
            CalibrationExample(
                actual_label=normalize_label(actual),
                predicted_label=normalize_label(predicted),
                confidence=float(confidence),
                sample_id=_row_id(row, index),
            )
        )
    identifiers = [item.sample_id for item in examples]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("O dataset de calibração contém IDs duplicados")
    return examples


def ensure_disjoint(calibration: list[CalibrationExample], holdout_path: Path) -> None:
    holdout_rows = _read_rows(holdout_path)
    holdout_ids = {_row_id(row, index) for index, row in enumerate(holdout_rows, start=1)}
    overlap = sorted({item.sample_id for item in calibration} & holdout_ids)
    if overlap:
        preview = ", ".join(overlap[:5])
        raise ValueError(f"Calibração e teste não são disjuntos; IDs repetidos: {preview}")


def result_payload(result: CalibrationResult, model: str) -> dict[str, Any]:
    return {
        "lambda_hat": result.lambda_hat,
        "alpha": result.alpha,
        "n": result.n,
        "model": model,
        "empirical_false_positive_risk": result.empirical_risk,
        "conditional_false_positive_rate": result.conditional_false_positive_rate,
        "false_positives": result.false_positives,
        "risk_bound": result.risk_bound,
    }


def persist(result: CalibrationResult, model: str, database_url: str) -> None:
    from sqlalchemy import create_engine

    from app.repositories.crc_calibration import CRCCalibrationRepository

    repository = CRCCalibrationRepository(create_engine(database_url))
    repository.save(
        CRCCalibration(
            lambda_hat=result.lambda_hat,
            alpha=result.alpha,
            n=result.n,
            model=model,
            created_at=datetime.now(timezone.utc),  # noqa: UP017 -- compatível com Python 3.9
        )
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path, help="CSV ou JSON com rótulo, predição e confiança")
    parser.add_argument("--model", required=True, help="Modelo ao qual a calibração se aplica")
    parser.add_argument("--alpha", type=float, default=0.05)
    parser.add_argument("--holdout", type=Path, help="Dataset da #27 para validar disjunção por ID")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", ""))
    parser.add_argument("--output", type=Path, help="Arquivo JSON para o relatório")
    parser.add_argument("--dry-run", action="store_true", help="Calcula sem gravar no banco")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    examples = load_examples(args.dataset)
    if args.holdout:
        ensure_disjoint(examples, args.holdout)
    result = calibrate_threshold(examples, alpha=args.alpha)
    payload = result_payload(result, args.model)

    if not args.dry_run:
        if not args.database_url:
            raise SystemExit("DATABASE_URL ou --database-url é obrigatório sem --dry-run")
        persist(result, args.model, args.database_url)
        payload["persisted"] = True
    else:
        payload["persisted"] = False

    rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
