"""Testes do carregamento de datasets para calibração CRC."""

import json

import pytest
from experiments.calibrate_crc import ensure_disjoint, load_examples, normalize_label


def test_maps_portuguese_textual_rating_and_loads_json(tmp_path):
    dataset = tmp_path / "calibration.json"
    dataset.write_text(
        json.dumps(
            [
                {
                    "id": "claim-1",
                    "textualRating": "Verdadeiro",
                    "predicted_label": "Falso",
                    "confidence": 0.7,
                }
            ]
        ),
        encoding="utf-8",
    )

    examples = load_examples(dataset)

    assert examples[0].actual_label == "true"
    assert examples[0].predicted_label == "false"
    assert normalize_label("Enganoso") == "misleading"


def test_rejects_overlap_with_issue_27_holdout(tmp_path):
    calibration_path = tmp_path / "calibration.json"
    holdout_path = tmp_path / "holdout.json"
    calibration_path.write_text(
        json.dumps(
            [
                {
                    "id": "same-claim",
                    "actual_label": "true",
                    "predicted_label": "true",
                    "confidence": 0.9,
                }
            ]
        ),
        encoding="utf-8",
    )
    holdout_path.write_text(json.dumps([{"id": "same-claim"}]), encoding="utf-8")

    with pytest.raises(ValueError, match="não são disjuntos"):
        ensure_disjoint(load_examples(calibration_path), holdout_path)
