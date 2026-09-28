"""Avalia e recalibra o bot score contra contas Bluesky rotuladas (#18).

O arquivo de entrada deve ser CSV ou JSON e conter ``label`` (0 humano, 1 bot)
e as mesmas colunas calculadas por ``app.domain.bot_features.compute_all_features``.
Dados sintéticos não são aceitos: métricas de validação devem representar contas
reais e rotuladas. Por padrão o arquivo é procurado em
``research/datasets/data/bluesky_bot_labels.csv`` (ignorado pelo Git).
"""

import argparse
import json
import math
from pathlib import Path

import pandas as pd
import yaml
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import confusion_matrix, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import train_test_split

EXPERIMENTS_DIR = Path(__file__).resolve().parent
DATA_DIR = EXPERIMENTS_DIR.parent / "datasets" / "data"
RESULTS_DIR = EXPERIMENTS_DIR / "results"
WEIGHTS_FILE = EXPERIMENTS_DIR.parent.parent / "api" / "app" / "domain" / "bot_weights.yaml"

# Contrato do scorer em produção; mantenha em sincronia com bot_features.py.
FEATURES = (
    "demographic_young_account",
    "demographic_digits_handle",
    "demographic_no_avatar",
    "demographic_no_description",
    "demographic_self_label_bot",
    "network_follower_ratio",
    "temporal_posts_per_day",
    "temporal_interval_cv",
    "temporal_hour_entropy",
    "content_duplicate_ratio",
    "content_repost_ratio",
    "content_repeated_links",
)


def load_dataset(path: Path) -> tuple[pd.DataFrame, pd.Series]:
    """Carrega labels binários e rejeita dados incompletos ou sem classes."""
    if not path.exists():
        raise FileNotFoundError(
            f"Dataset rotulado não encontrado: {path}. "
            "Colete contas self-labelled bot e uma amostra humana antes de avaliar."
        )
    frame = pd.read_json(path) if path.suffix.lower() == ".json" else pd.read_csv(path)
    missing = {"label", *FEATURES}.difference(frame.columns)
    if missing:
        raise ValueError(f"Dataset sem as colunas obrigatórias: {', '.join(sorted(missing))}")

    labels = pd.to_numeric(frame["label"], errors="raise").astype(int)
    if not set(labels.unique()).issubset({0, 1}) or labels.nunique() != 2:
        raise ValueError("label deve conter as duas classes binárias: 0 (humano) e 1 (bot)")
    if labels.value_counts().min() < 2:
        raise ValueError("Cada classe precisa de ao menos duas contas para a divisão estratificada")

    values = frame.loc[:, FEATURES].apply(pd.to_numeric, errors="raise")
    if values.isna().any().any():
        raise ValueError("Features não podem conter valores ausentes")
    return values, labels


def score_with_current_weights(values: pd.DataFrame, weights: dict[str, float]) -> pd.Series:
    bias = float(weights.get("bias", -2.0))
    linear = sum(values[name] * float(weights.get(name, 0.0)) for name in FEATURES) + bias
    return linear.map(lambda value: 1 / (1 + math.exp(-value)))


def metrics_for(labels: pd.Series, probabilities: pd.Series) -> dict[str, object]:
    predictions = (probabilities >= 0.9).astype(int)
    return {
        "roc_auc": float(roc_auc_score(labels, probabilities)),
        "precision_at_0_9": float(precision_score(labels, predictions, zero_division=0)),
        "recall_at_0_9": float(recall_score(labels, predictions, zero_division=0)),
        "confusion_matrix_at_0_9": confusion_matrix(labels, predictions).tolist(),
    }


def evaluate(dataset: Path, test_size: float = 0.2, random_state: int = 42) -> dict[str, object]:
    values, labels = load_dataset(dataset)
    train_x, test_x, train_y, test_y = train_test_split(
        values, labels, test_size=test_size, random_state=random_state, stratify=labels
    )
    with WEIGHTS_FILE.open(encoding="utf-8") as fh:
        current_weights = yaml.safe_load(fh)["weights"]

    model = LogisticRegression(max_iter=1000, class_weight="balanced", random_state=random_state)
    model.fit(train_x, train_y)
    proposed_weights = dict(zip(FEATURES, model.coef_[0], strict=True))
    proposed_weights["bias"] = float(model.intercept_[0])

    return {
        "dataset": str(dataset),
        "train_size": len(train_x),
        "test_size": len(test_x),
        "threshold": 0.9,
        "current_weights_holdout": metrics_for(
            test_y, score_with_current_weights(test_x, current_weights)
        ),
        "recalibrated_holdout": metrics_for(
            test_y, pd.Series(model.predict_proba(test_x)[:, 1], index=test_x.index)
        ),
        "proposed_weights": {name: float(weight) for name, weight in proposed_weights.items()},
    }


def write_results(result: dict[str, object], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "bot_score_metrics.json").open("w", encoding="utf-8") as fh:
        metrics = {key: value for key, value in result.items() if key != "proposed_weights"}
        json.dump(metrics, fh, indent=2)
    with (output_dir / "bot_score_new_weights.json").open("w", encoding="utf-8") as fh:
        json.dump(result["proposed_weights"], fh, indent=2)

    calibrated = result["recalibrated_holdout"]
    assert isinstance(calibrated, dict)
    summary = (
        "# Avaliação de Bot Score\n\n"
        "Métricas calculadas em holdout estratificado de contas Bluesky rotuladas; "
        "nenhuma métrica usa exemplos de treino.\n\n"
        "## Recalibrado — holdout\n"
        f"- ROC-AUC: {calibrated['roc_auc']:.4f}\n"
        f"- Precisão @ 0,9: {calibrated['precision_at_0_9']:.4f}\n"
        f"- Recall @ 0,9: {calibrated['recall_at_0_9']:.4f}\n"
    )
    (output_dir / "bot_score_summary.md").write_text(summary, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DATA_DIR / "bluesky_bot_labels.csv")
    parser.add_argument("--output-dir", type=Path, default=RESULTS_DIR)
    args = parser.parse_args()
    write_results(evaluate(args.dataset), args.output_dir)


if __name__ == "__main__":
    main()
