"""Smoke test de recuperação: não é avaliação de veracidade nem benchmark da #27."""

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine

from app.clients.evidence.embeddings import MODEL_NAME
from app.clients.evidence.rss_checkers import RSSCheckersSource
from app.core.config import get_settings
from app.repositories.fact_articles import FactArticleRepository


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--min-articles", type=int, default=100)
    args = parser.parse_args()
    cases = json.loads(args.cases.read_text())
    if len(cases) < 5:
        raise SystemExit("Forneça ao menos cinco alegações com expected_url")
    settings = get_settings()
    engine = create_engine(settings.database_url)
    try:
        repository = FactArticleRepository(engine)
        source = RSSCheckersSource(settings, repository=repository)
        report = {
            "checked_at": datetime.now(UTC).isoformat(),
            "model": MODEL_NAME,
            "articles": repository.count(),
            "cases": [],
        }
        for case in cases:
            evidence = await source.search(case["claim"], limit=5)
            urls = [e.url for e in evidence]
            report["cases"].append(
                {**case, "retrieved_urls": urls, "passed": case["expected_url"] in urls}
            )
        report["passed"] = report["articles"] >= args.min_articles and all(
            case["passed"] for case in report["cases"]
        )
        output = json.dumps(report, indent=2, ensure_ascii=False)
        if args.output:
            args.output.write_text(output + "\n")
        print(output)
        if not report["passed"]:
            raise SystemExit(1)
    finally:
        engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
