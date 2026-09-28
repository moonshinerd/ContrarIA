"""Avalia a #22 com um modelo real e o conjunto dourado anotado."""

import argparse
import asyncio
import json
import re
import unicodedata
from datetime import UTC, date, datetime
from difflib import SequenceMatcher
from pathlib import Path

from app.core.config import get_settings
from app.models.llm.litellm_model import LiteLLMModel
from app.services.claim_verification import ClaimVerificationPlanner, PostContext


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.casefold())
    value = "".join(char for char in value if not unicodedata.combining(char))
    return " ".join(re.findall(r"[\w%]+", value))


def keyword_matches(keyword: str, text: str) -> bool:
    normalized_keyword = normalize_text(keyword)
    normalized_text = normalize_text(text)
    if normalized_keyword in normalized_text:
        return True
    if " " in normalized_keyword:
        return False
    return any(
        SequenceMatcher(None, normalized_keyword, token).ratio() >= 0.8
        for token in normalized_text.split()
    )


def item_matches(actual, expected) -> bool:
    return (
        actual.source.value == expected["source"]
        and actual.classification.value == expected["classification"]
        and all(keyword_matches(keyword, actual.text) for keyword in expected["keywords"])
    )


def extraction_matches(actual, expected) -> bool:
    remaining = list(actual)
    for annotated in expected:
        match_index = next(
            (index for index, item in enumerate(remaining) if item_matches(item, annotated)),
            None,
        )
        if match_index is None:
            return False
        remaining.pop(match_index)
    return not any(item.classification.value == "factual" for item in remaining)


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--date", type=date.fromisoformat, default=date.today())
    args = parser.parse_args()

    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    planner = ClaimVerificationPlanner(LiteLLMModel(get_settings()))
    report = {
        "checked_at": datetime.now(UTC).isoformat(),
        "model": get_settings().llm_model_name,
        "cases": [],
    }
    for case in cases:
        try:
            plan = await planner.plan(
                PostContext.model_validate(case["context"]), current_date=args.date
            )
            extraction = plan.extraction
            actual = extraction.items
            extraction_passed = extraction_matches(actual, case["expected"])
            expected_factual_count = sum(
                item["classification"] == "factual" for item in case["expected"]
            )
            cove_passed = (
                plan.cove is None
                if expected_factual_count == 0
                else plan.cove is not None
                and len(plan.cove.claims) == expected_factual_count
                and all(len(claim.questions) >= 2 for claim in plan.cove.claims)
            )
            passed = extraction_passed and cove_passed
            report["cases"].append(
                {
                    "id": case["id"],
                    "passed": passed,
                    "extraction_passed": extraction_passed,
                    "cove_passed": cove_passed,
                    "actual": [item.model_dump(mode="json") for item in actual],
                    "cove": plan.cove.model_dump(mode="json") if plan.cove else None,
                }
            )
        except Exception as exc:
            report["cases"].append({"id": case["id"], "passed": False, "error": type(exc).__name__})
    report["passed_count"] = sum(item["passed"] for item in report["cases"])
    report["total"] = len(report["cases"])
    report["required_pass_count"] = 10
    report["passed"] = report["total"] >= 10 and report["passed_count"] >= 10
    output = json.dumps(report, ensure_ascii=False, indent=2)
    print(output)
    if args.output:
        args.output.write_text(output + "\n", encoding="utf-8")
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
