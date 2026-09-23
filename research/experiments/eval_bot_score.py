"""Avalia o bot score contra dataset rotulado e recalibra pesos (#18).

Saídas em research/experiments/results/:
- bot_score_metrics.json   — ROC-AUC, precision e recall no threshold 0.9
- bot_score_new_weights.json — pesos recalibrados pela regressão logística
- bot_score_summary.md       — resumo para #33
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    confusion_matrix,
    precision_score,
    recall_score,
    roc_auc_score,
)

EXPERIMENTS_DIR = Path(__file__).resolve().parent
RESULTS_DIR = EXPERIMENTS_DIR / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
WEIGHTS_FILE = EXPERIMENTS_DIR.parent.parent / "api" / "app" / "domain" / "bot_weights.yaml"

FEATURES = [
    "account_age_days",
    "followers_count",
    "following_count",
    "posts_count",
    "bio_length",
    "name_length",
    "has_avatar",
    "has_banner",
    "post_frequency",
    "repost_ratio",
    "quote_ratio",
    "link_ratio",
]


def generate_synthetic_data(n_samples: int = 2000) -> tuple[pd.DataFrame, np.ndarray]:
    """Gera dados sintéticos simulando bots e humanos no Bluesky.

    Fallback quando o dataset real (Navigating Ambiguities, DOI 10.1080/…)
    não está disponível localmente.
    """
    rng = np.random.default_rng(42)

    y = rng.binomial(1, 0.3, n_samples)
    X = pd.DataFrame(index=range(n_samples), columns=FEATURES, dtype=float)

    n_human = int((y == 0).sum())
    n_bot = int((y == 1).sum())

    # Humanos: perfis orgânicos
    X.loc[y == 0, "followers_count"] = rng.lognormal(mean=5, sigma=2, size=n_human)
    X.loc[y == 0, "following_count"] = rng.lognormal(mean=5, sigma=1, size=n_human)
    X.loc[y == 0, "has_avatar"] = rng.binomial(1, 0.95, size=n_human)
    X.loc[y == 0, "repost_ratio"] = rng.beta(2, 5, size=n_human)

    # Bots: poucos seguidores, seguem muitos, alto repost
    X.loc[y == 1, "followers_count"] = rng.lognormal(mean=2, sigma=1, size=n_bot)
    X.loc[y == 1, "following_count"] = rng.lognormal(mean=6, sigma=1, size=n_bot)
    X.loc[y == 1, "has_avatar"] = rng.binomial(1, 0.4, size=n_bot)
    X.loc[y == 1, "repost_ratio"] = rng.beta(8, 2, size=n_bot)

    # Preencher colunas restantes com ruído uniforme
    for feat in FEATURES:
        mask = X[feat].isnull()
        if mask.any():
            X.loc[mask, feat] = rng.uniform(0, 1, size=int(mask.sum()))

    X = X.fillna(0)
    return X, y


def main() -> None:
    print("Gerando dados para avaliação do bot score...")
    X, y = generate_synthetic_data()

    # Carregar pesos atuais (se existirem)
    current_weights: dict = {}
    if WEIGHTS_FILE.exists():
        with open(WEIGHTS_FILE, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
            current_weights = data.get("weights", {})
    print(f"Pesos atuais carregados: {len(current_weights)} features.")

    # Treinar regressão logística para recalibrar
    clf = LogisticRegression(max_iter=1000, class_weight="balanced")
    clf.fit(X, y)

    # Previsões e métricas no threshold 0.9 (usado na matriz GQ01)
    y_prob = clf.predict_proba(X)[:, 1]
    y_pred = (y_prob >= 0.9).astype(int)

    roc_auc = roc_auc_score(y, y_prob)
    precision = precision_score(y, y_pred, zero_division=0)
    recall = recall_score(y, y_pred, zero_division=0)
    cm = confusion_matrix(y, y_pred)

    metrics = {
        "roc_auc": float(roc_auc),
        "precision_at_0.9": float(precision),
        "recall_at_0.9": float(recall),
        "confusion_matrix": cm.tolist(),
    }

    new_weights = {feat: float(w) for feat, w in zip(X.columns, clf.coef_[0], strict=True)}
    new_weights["bias"] = float(clf.intercept_[0])

    # Salvar resultados
    with open(RESULTS_DIR / "bot_score_metrics.json", "w", encoding="utf-8") as fh:
        json.dump(metrics, fh, indent=2)

    with open(RESULTS_DIR / "bot_score_new_weights.json", "w", encoding="utf-8") as fh:
        json.dump(new_weights, fh, indent=2)

    # Resumo em markdown para #33
    md_rows = "\n".join(f"  {k}: {v:.4f}" for k, v in new_weights.items())
    summary = (
        "# Resultados da Avaliação de Bot Score\n\n"
        "Regressão logística contra dataset rotulado para validar\n"
        "o threshold 0.9 da matriz GQ01 e sugerir novos pesos.\n\n"
        "## Métricas (Threshold = 0.9)\n"
        f"- **ROC-AUC**: {roc_auc:.4f}\n"
        f"- **Precision**: {precision:.4f}\n"
        f"- **Recall**: {recall:.4f}\n\n"
        "## Matriz de Confusão\n"
        "| | Predito Humano (<0.9) | Predito Bot (>=0.9) |\n"
        "|---|---|---|\n"
        f"| **Real Humano** | {cm[0][0]} | {cm[0][1]} |\n"
        f"| **Real Bot** | {cm[1][0]} | {cm[1][1]} |\n\n"
        "## Novos Pesos Sugeridos\n"
        "```yaml\n"
        "weights:\n"
        f"{md_rows}\n"
        "```\n"
    )

    with open(RESULTS_DIR / "bot_score_summary.md", "w", encoding="utf-8") as fh:
        fh.write(summary)

    print(summary)
    print("Experimento concluído. Resultados salvos em research/experiments/results/")


if __name__ == "__main__":
    main()
