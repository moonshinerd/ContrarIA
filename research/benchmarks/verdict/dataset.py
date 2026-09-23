"""Contrato e carregamento do conjunto ClaimReview da issue #27."""

import csv
import hashlib
import json
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

VERDICT_LABELS = ("false", "misleading", "true")


def _normalized(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value).strip().casefold())
    return " ".join("".join(char for char in text if not unicodedata.combining(char)).split())


def normalize_textual_rating(value: Any) -> str:
    """Mapeia avaliações livres em português para os três rótulos do benchmark."""
    rating = _normalized(value).replace("_", " ")
    false_markers = ("falso", "falsa", "errado", "errada", "fake", "nao procede")
    misleading_markers = (
        "enganoso",
        "enganosa",
        "enganador",
        "enganadora",
        "nao e bem assim",
        "distorcido",
        "distorcida",
        "fora de contexto",
        "impreciso",
        "imprecisa",
        "exagerado",
        "exagerada",
    )
    true_markers = (
        "verdadeiro",
        "verdadeira",
        "correto",
        "correta",
        "comprovado",
        "comprovada",
        "praticamente certo",
        "procede",
        "e verdade",
        "certo",
        "certa",
    )
    if "nao e verdade" in rating or any(marker in rating for marker in false_markers):
        return "false"
    if any(marker in rating for marker in misleading_markers):
        return "misleading"
    if any(marker in rating for marker in true_markers):
        return "true"
    raise ValueError(f"textualRating não mapeado: {value!r}")


def stable_claim_id(claim: str, review_url: str, publisher: str) -> str:
    identity = "\n".join((claim.strip(), review_url.strip(), publisher.strip())).casefold()
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]


@dataclass(frozen=True)
class BenchmarkClaim:
    claim_id: str
    claim: str
    expected_label: str
    textual_rating: str
    review_url: str
    publisher: str
    review_date: str = ""


def read_rows(path: Path) -> list[dict[str, Any]]:
    suffix = path.suffix.casefold()
    if suffix == ".csv":
        with path.open(encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))
    if suffix == ".jsonl":
        with path.open(encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if isinstance(payload, dict):
        payload = payload.get("items", payload.get("claims"))
    if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
        raise ValueError("Dataset deve ser CSV, JSONL ou uma lista JSON")
    return payload


def row_id(row: dict[str, Any]) -> str:
    explicit = row.get("id") or row.get("claim_id") or row.get("sample_id")
    if explicit:
        return str(explicit)
    return stable_claim_id(
        str(row.get("claim", row.get("text", ""))),
        str(row.get("review_url", row.get("url", ""))),
        str(row.get("publisher", "")),
    )


def row_keys(row: dict[str, Any]) -> set[str]:
    """Identidades alternativas para detectar sobreposição entre splits."""
    keys = {f"id:{row_id(row)}"}
    url = str(row.get("review_url", row.get("url", ""))).strip().casefold().rstrip("/")
    claim = _normalized(row.get("claim", row.get("text", "")))
    if url:
        keys.add(f"url:{url}")
    if claim:
        keys.add(f"claim:{claim}")
    return keys


def load_claims(
    path: Path,
    *,
    calibration_path: Path | None = None,
    limit: int | None = None,
) -> list[BenchmarkClaim]:
    rows = read_rows(path)
    calibration_keys: set[str] = set()
    if calibration_path:
        calibration_keys = {key for row in read_rows(calibration_path) for key in row_keys(row)}

    claims: list[BenchmarkClaim] = []
    seen: set[str] = set()
    for index, row in enumerate(rows, start=1):
        claim = str(row.get("claim", row.get("text", ""))).strip()
        review_url = str(row.get("review_url", row.get("url", ""))).strip()
        publisher = str(row.get("publisher", "")).strip()
        textual_rating = str(
            row.get("textualRating", row.get("textual_rating", row.get("rating", "")))
        ).strip()
        if not claim or not textual_rating or not review_url or not publisher:
            raise ValueError(
                f"Linha {index}: claim, textualRating, review_url e publisher são obrigatórios"
            )
        expected = str(row.get("label", "")).strip().casefold()
        if not expected:
            expected = normalize_textual_rating(textual_rating)
        if expected not in VERDICT_LABELS:
            raise ValueError(f"Linha {index}: label inválido: {expected!r}")

        claim_id = row_id(row)
        if claim_id in seen:
            raise ValueError(f"Dataset contém ID duplicado: {claim_id}")
        if calibration_keys & row_keys(row):
            raise ValueError(f"Dataset de teste não é disjunto da calibração: {claim_id}")
        seen.add(claim_id)
        claims.append(
            BenchmarkClaim(
                claim_id=claim_id,
                claim=claim,
                expected_label=expected,
                textual_rating=textual_rating,
                review_url=review_url,
                publisher=publisher,
                review_date=str(row.get("review_date", row.get("reviewDate", ""))),
            )
        )
        if limit is not None and len(claims) >= limit:
            break

    if not claims:
        raise ValueError("Dataset de benchmark está vazio")
    return claims
