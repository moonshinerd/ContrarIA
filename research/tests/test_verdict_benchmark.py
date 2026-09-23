"""Testes do benchmark de veredito e ablação da issue #27."""

import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest
from benchmarks.verdict.dataset import load_claims, normalize_textual_rating
from benchmarks.verdict.leakage import is_origin_evidence
from benchmarks.verdict.metrics import compute_metrics
from benchmarks.verdict.scenarios import build_scenarios

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_normalizes_claimreview_ratings_in_portuguese():
    assert normalize_textual_rating("Falso") == "false"
    assert normalize_textual_rating("não_é_bem_assim") == "misleading"
    assert normalize_textual_rating("É VERDADE que a cobrança existe") == "true"
    with pytest.raises(ValueError, match="não mapeado"):
        normalize_textual_rating("sem classificação")


def test_dataset_must_be_disjoint_from_crc_calibration(tmp_path):
    row = {
        "id": "claim-1",
        "claim": "Alegação verificável",
        "textualRating": "Falso",
        "review_url": "https://checagem.example/1",
        "publisher": "Checagem",
    }
    dataset = tmp_path / "test.jsonl"
    calibration = tmp_path / "calibration.json"
    dataset.write_text(json.dumps(row) + "\n", encoding="utf-8")
    calibration.write_text(
        json.dumps([{"url": row["review_url"], "actual_label": "false"}]),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="não é disjunto"):
        load_claims(dataset, calibration_path=calibration)


def test_builds_every_single_source_and_leave_one_out_scenario():
    sources = ["google_factcheck", "wikipedia", "tavily", "duckduckgo", "rss_checkers"]

    scenarios = build_scenarios(sources)

    assert len(scenarios) == 17
    assert any(item.name == "only_wikipedia" for item in scenarios)
    assert any(item.name == "without_rss_checkers" for item in scenarios)
    assert all("google_factcheck" in item.sources for item in scenarios if item.exclude_origin)


@pytest.mark.parametrize(
    ("url", "title", "snippet"),
    [
        ("https://www.aosfatos.org/check/1?utm_source=x", "Outro título", "Outro texto"),
        ("https://www.aosfatos.org/check/2", "Outro título", "Outro texto"),
        ("https://example.org/noticia", "Checagem por Aos Fatos", "Outro texto"),
    ],
)
def test_excludes_origin_url_domain_and_publisher(url, title, snippet):
    assert is_origin_evidence(
        evidence_url=url,
        title=title,
        snippet=snippet,
        origin_url="https://aosfatos.org/check/1",
        publisher="Aos Fatos",
    )


def test_computes_required_metrics_with_abstention_and_false_positive():
    rows = [
        {
            "expected_label": "true",
            "predicted_label": "false",
            "latency_seconds": 1.0,
            "cost_usd": 0.01,
            "error": "",
        },
        {
            "expected_label": "false",
            "predicted_label": "false",
            "latency_seconds": 2.0,
            "cost_usd": 0.02,
            "error": "",
        },
        {
            "expected_label": "misleading",
            "predicted_label": "insufficient_evidence",
            "latency_seconds": 3.0,
            "cost_usd": 0.03,
            "error": "",
        },
    ]

    metrics = compute_metrics(rows)

    assert metrics["accuracy"] == pytest.approx(1 / 3)
    assert metrics["macro_f1"] == pytest.approx(2 / 9)
    assert metrics["false_positive_rate"] == 1.0
    assert metrics["abstention_rate"] == pytest.approx(1 / 3)
    assert metrics["coverage"] == pytest.approx(2 / 3)
    assert metrics["selective_accuracy"] == 0.5
    assert metrics["cost_usd"] == pytest.approx(0.06)
    assert metrics["latency_mean_seconds"] == 2.0


def test_replay_generates_csv_and_markdown_tables(tmp_path):
    output = tmp_path / "results"
    config = tmp_path / "benchmark.yaml"
    dataset = REPOSITORY_ROOT / "research/benchmarks/verdict/fixtures/claims_smoke.jsonl"
    config.write_text(
        "\n".join(
            [
                f"dataset: {dataset}",
                f"output_dir: {output}",
                "calibration_dataset: null",
                "model: openrouter/google/gemini-2.5-flash",
                "evaluation_date: 2026-09-24",
                "lambda_hat: 0.80",
                "alpha: 0.05",
                "sources: [google_factcheck, wikipedia, tavily, duckduckgo, rss_checkers]",
                "ablation:",
                "  include_all: true",
                "  individual: true",
                "  leave_one_out: true",
                "  repeat_without_origin: true",
                "runtime:",
                "  debate_rounds: 1",
                "  p_ik_threshold: 0.60",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    script = REPOSITORY_ROOT / "research/benchmarks/verdict/run_benchmark.py"
    predictions = REPOSITORY_ROOT / "research/benchmarks/verdict/fixtures/predictions_smoke.csv"

    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--config",
            str(config),
            "--predictions",
            str(predictions),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    with (output / "metrics.csv").open(encoding="utf-8", newline="") as handle:
        metrics = list(csv.DictReader(handle))
    assert len(metrics) == 17
    assert (output / "predictions.csv").exists()
    assert "| Cenário |" in (output / "summary.md").read_text(encoding="utf-8")
