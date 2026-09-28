"""Métricas seletivas do benchmark de vereditos."""

import math
from collections import defaultdict
from statistics import mean
from typing import Any

TARGET_LABELS = ("false", "misleading", "true")
ABSTENTION_LABEL = "insufficient_evidence"


def _safe_div(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _macro_f1(rows: list[dict[str, Any]]) -> float:
    scores: list[float] = []
    for label in TARGET_LABELS:
        true_positive = sum(
            row["expected_label"] == label and row["predicted_label"] == label for row in rows
        )
        false_positive = sum(
            row["expected_label"] != label and row["predicted_label"] == label for row in rows
        )
        false_negative = sum(
            row["expected_label"] == label and row["predicted_label"] != label for row in rows
        )
        precision = _safe_div(true_positive, true_positive + false_positive)
        recall = _safe_div(true_positive, true_positive + false_negative)
        scores.append(_safe_div(2 * precision * recall, precision + recall))
    return mean(scores)


def compute_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        raise ValueError("Não há predições para calcular métricas")
    n = len(rows)
    covered = [row for row in rows if row["predicted_label"] != ABSTENTION_LABEL]
    true_rows = [row for row in rows if row["expected_label"] == "true"]
    false_positives = [row for row in true_rows if row["predicted_label"] == "false"]
    latencies = [float(row["latency_seconds"]) for row in rows]
    costs = [float(row["cost_usd"]) for row in rows]

    return {
        "n": n,
        "accuracy": _safe_div(
            sum(row["predicted_label"] == row["expected_label"] for row in rows), n
        ),
        "macro_f1": _macro_f1(rows),
        "false_positive_rate": _safe_div(len(false_positives), len(true_rows)),
        "false_positives": len(false_positives),
        "true_claims": len(true_rows),
        "abstention_rate": _safe_div(n - len(covered), n),
        "coverage": _safe_div(len(covered), n),
        "selective_accuracy": _safe_div(
            sum(row["predicted_label"] == row["expected_label"] for row in covered),
            len(covered),
        ),
        "cost_usd": sum(costs),
        "cost_per_claim_usd": mean(costs),
        "latency_mean_seconds": mean(latencies),
        "latency_p95_seconds": _percentile(latencies, 0.95),
        "errors": sum(bool(row.get("error")) for row in rows),
    }


def group_metrics(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, bool, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        key = (str(row["scenario"]), bool(row["exclude_origin"]), str(row["sources"]))
        grouped[key].append(row)

    result = []
    for (scenario, exclude_origin, sources), items in sorted(grouped.items()):
        result.append(
            {
                "scenario": scenario,
                "exclude_origin": exclude_origin,
                "sources": sources,
                **compute_metrics(items),
            }
        )
    return result
