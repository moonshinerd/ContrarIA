import pandas as pd
from experiments.eval_bot_score import FEATURES, evaluate


def test_evaluate_uses_a_stratified_holdout(tmp_path):
    rows = []
    for label in (0, 1):
        for index in range(10):
            row = {feature: float(label) for feature in FEATURES}
            row["demographic_digits_handle"] = index / 10
            row["label"] = label
            rows.append(row)
    dataset = tmp_path / "labels.csv"
    pd.DataFrame(rows).to_csv(dataset, index=False)

    result = evaluate(dataset, test_size=0.2, random_state=7)

    assert result["train_size"] == 16
    assert result["test_size"] == 4
    assert set(result["proposed_weights"]) == {*FEATURES, "bias"}
    assert "roc_auc" in result["recalibrated_holdout"]
