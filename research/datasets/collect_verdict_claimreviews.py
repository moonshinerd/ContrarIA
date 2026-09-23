"""Coleta ClaimReviews PT-BR para o conjunto de teste da issue #27."""

import argparse
import asyncio
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
API_ROOT = REPOSITORY_ROOT / "api"
for import_root in (REPOSITORY_ROOT, API_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from research.benchmarks.verdict.dataset import (  # noqa: E402
    normalize_textual_rating,
    read_rows,
    row_keys,
    stable_claim_id,
)

from app.core.config import Settings  # noqa: E402

DEFAULT_QUERIES = [
    "verdadeiro",
    "é verdade",
    "comprovado",
    "correto",
    "certo",
    "fato",
    "real",
    "verídico",
    "procede",
    "eleições Brasil",
    "urna eletrônica",
    "vacina",
    "Lula",
    "Bolsonaro",
    "STF",
    "saúde Brasil",
    "economia Brasil",
    "TSE",
    "fake news Brasil",
]


async def _fetch(query: str, *, api_key: str, page_size: int) -> list[dict[str, Any]]:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                "https://factchecktools.googleapis.com/v1alpha1/claims:search",
                params={
                    "query": query,
                    "languageCode": "pt",
                    "pageSize": page_size,
                    "key": api_key,
                },
            )
            if response.status_code >= 400:
                raise RuntimeError(f"Google Fact Check respondeu HTTP {response.status_code}")
            payload = response.json()
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Falha de rede na consulta {query!r}: {type(exc).__name__}") from None
    return list(payload.get("claims", []))


def _records(claims: list[dict[str, Any]], query: str) -> tuple[list[dict[str, Any]], int]:
    records: list[dict[str, Any]] = []
    unmapped = 0
    for claim in claims:
        claim_text = str(claim.get("text", "")).strip()
        if urlsplit(claim_text).scheme in {"http", "https"}:
            continue
        for review in claim.get("claimReview", []):
            rating = str(review.get("textualRating", "")).strip()
            publisher = str(review.get("publisher", {}).get("name", "")).strip()
            review_url = str(review.get("url", "")).strip()
            if not claim_text or not rating or not publisher or not review_url:
                continue
            hostname = (urlsplit(review_url).hostname or "").casefold()
            if hostname.endswith(".pt") or publisher.casefold() in {"observador", "polígrafo"}:
                continue
            try:
                label = normalize_textual_rating(rating)
            except ValueError:
                unmapped += 1
                continue
            records.append(
                {
                    "id": stable_claim_id(claim_text, review_url, publisher),
                    "claim": claim_text,
                    "textualRating": rating,
                    "label": label,
                    "review_url": review_url,
                    "publisher": publisher,
                    "review_date": review.get("reviewDate", ""),
                    "claim_date": claim.get("claimDate", ""),
                    "query": query,
                    "split": "test_issue_27",
                }
            )
    return records, unmapped


async def collect(queries: list[str], *, api_key: str, page_size: int) -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    unmapped = 0
    for query in queries:
        records, skipped = _records(
            await _fetch(query, api_key=api_key, page_size=page_size), query
        )
        unmapped += skipped
        for record in records:
            unique.setdefault(record["id"], record)
    print(f"ClaimReviews mapeados: {len(unique)}; avaliações não mapeadas: {unmapped}")
    return list(unique.values())


def _select(records: list[dict[str, Any]], maximum: int) -> list[dict[str, Any]]:
    by_label: dict[str, list[dict[str, Any]]] = {
        label: [] for label in ("true", "false", "misleading")
    }
    for record in records:
        by_label[record["label"]].append(record)
    for items in by_label.values():
        items.sort(key=lambda row: row["id"])

    # Alegações verdadeiras são raras nas plataformas de checagem; preservamos
    # todas e dividimos as vagas restantes entre falso e enganoso.
    selected = list(by_label["true"])
    remaining = max(maximum - len(selected), 0)
    false_quota = (remaining + 1) // 2
    selected.extend(by_label["false"][:false_quota])
    selected.extend(by_label["misleading"][: remaining - false_quota])
    if len(selected) < maximum:
        selected_ids = {row["id"] for row in selected}
        leftovers = sorted(
            (row for row in records if row["id"] not in selected_ids),
            key=lambda row: row["id"],
        )
        selected.extend(leftovers[: maximum - len(selected)])
    return sorted(selected[:maximum], key=lambda row: row["id"])


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--calibration", type=Path)
    parser.add_argument("--query", action="append", dest="queries")
    parser.add_argument("--page-size", type=int, default=20)
    parser.add_argument("--max-items", type=int, default=150)
    return parser


def main() -> int:
    args = _parser().parse_args()
    settings = Settings()
    if not settings.google_factcheck_api_key:
        raise SystemExit("GOOGLE_FACTCHECK_API_KEY é obrigatória")
    records = asyncio.run(
        collect(
            args.queries or DEFAULT_QUERIES,
            api_key=settings.google_factcheck_api_key,
            page_size=args.page_size,
        )
    )
    selected = _select(records, args.max_items)
    if args.calibration:
        calibration_keys = {key for row in read_rows(args.calibration) for key in row_keys(row)}
        overlap = [row["id"] for row in selected if calibration_keys & row_keys(row)]
        if overlap:
            raise SystemExit(f"Dataset não é disjunto da calibração: {len(overlap)} IDs repetidos")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        for record in selected:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"Dataset salvo em {args.output}: {dict(Counter(row['label'] for row in selected))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
