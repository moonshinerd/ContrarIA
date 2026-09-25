"""Testes das funções puras de exportação do dataset de calibração."""

import csv

from experiments.export_calibration_dataset import (
    CSV_FIELDS,
    append_rows,
    claim_id_for,
    error_flag,
    load_existing_claim_ids,
    sources_used,
)


def test_claim_id_for_uses_post_rkey():
    uri = "at://did:plc:abc123/app.bsky.feed.post/3mw7yoquw722w"
    assert claim_id_for(uri) == "bsky:3mw7yoquw722w"


def test_sources_used_collects_unique_sources_from_self_rag_outputs():
    agent_outputs = {
        "self_rag.q01.[Sources]": (
            '{"evidence": [{"source": "tavily"}, {"source": "wikipedia"}], "source_errors": {}}'
        ),
        "self_rag.q02.[Sources]": '{"evidence": [{"source": "tavily"}], "source_errors": {}}',
        "claim_extraction": "{}",
    }

    assert sources_used(agent_outputs) == "tavily+wikipedia"


def test_sources_used_returns_empty_without_agent_outputs():
    assert sources_used(None) == ""
    assert sources_used({}) == ""


def test_error_flag_detects_failure_key():
    assert error_flag({"self_rag.failure": "StructuredSelfRAGOutputError"}) == (
        "StructuredSelfRAGOutputError"
    )
    assert error_flag({"claim_extraction": "{}"}) == ""
    assert error_flag(None) == ""


def test_load_existing_claim_ids_reads_csv(tmp_path):
    csv_path = tmp_path / "calibration.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerow({field: "" for field in CSV_FIELDS} | {"claim_id": "existing-1"})

    assert load_existing_claim_ids(csv_path) == {"existing-1"}
    assert load_existing_claim_ids(tmp_path / "missing.csv") == set()


def test_append_rows_preserves_existing_rows(tmp_path):
    csv_path = tmp_path / "calibration.csv"
    first_row = {field: "" for field in CSV_FIELDS} | {
        "claim_id": "existing-1",
        "expected_label": "false",
    }
    append_rows(csv_path, [first_row])

    second_row = {field: "" for field in CSV_FIELDS} | {
        "claim_id": "novo-1",
        "expected_label": "true",
    }
    append_rows(csv_path, [second_row])

    with csv_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert [row["claim_id"] for row in rows] == ["existing-1", "novo-1"]
    assert rows[0]["expected_label"] == "false"
    assert rows[1]["expected_label"] == "true"
