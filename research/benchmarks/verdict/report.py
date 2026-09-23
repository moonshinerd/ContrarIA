"""Persistência dos resultados detalhados e da tabela consumida pela #33."""

import csv
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PREDICTION_COLUMNS = [
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

METRIC_COLUMNS = [
    "scenario",
    "exclude_origin",
    "sources",
    "n",
    "accuracy",
    "macro_f1",
    "false_positive_rate",
    "false_positives",
    "true_claims",
    "abstention_rate",
    "coverage",
    "selective_accuracy",
    "cost_usd",
    "cost_per_claim_usd",
    "latency_mean_seconds",
    "latency_p95_seconds",
    "errors",
]


def _write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=columns,
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def render_markdown(metrics: list[dict[str, Any]]) -> str:
    lines = [
        "# Benchmark de veredito e ablação de fontes",
        "",
        "| Cenário | Sem origem | Acurácia | Macro-F1 | FP | Abstenção | "
        "Cobertura | USD/claim | Latência média (s) |",
        "|---|:---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in metrics:
        lines.append(
            "| {scenario} | {exclude} | {accuracy:.3f} | {macro_f1:.3f} | "
            "{false_positive_rate:.3f} | {abstention_rate:.3f} | {coverage:.3f} | "
            "{cost_per_claim_usd:.6f} | {latency_mean_seconds:.3f} |".format(
                exclude="sim" if row["exclude_origin"] else "não",
                **row,
            )
        )
    lines.extend(
        [
            "",
            "Acurácia e macro-F1 consideram abstenções como erro. FP é a fração de "
            "alegações verdadeiras classificadas como `false`. Cobertura é `1 - abstenção`.",
            "",
        ]
    )
    return "\n".join(lines)


def write_results(
    output_dir: Path,
    predictions: list[dict[str, Any]],
    metrics: list[dict[str, Any]],
    *,
    metadata: dict[str, Any],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(output_dir / "predictions.csv", predictions, PREDICTION_COLUMNS)
    _write_csv(output_dir / "metrics.csv", metrics, METRIC_COLUMNS)
    (output_dir / "summary.md").write_text(render_markdown(metrics), encoding="utf-8")
    (output_dir / "metadata.json").write_text(
        json.dumps(
            {"generated_at": datetime.now(UTC).isoformat(), **metadata},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
