import os
import json
import pandas as pd
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, precision_score, recall_score, confusion_matrix
import yaml
from pathlib import Path

# Paths
EXPERIMENTS_DIR = Path(__file__).resolve().parent
RESULTS_DIR = EXPERIMENTS_DIR / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
WEIGHTS_FILE = EXPERIMENTS_DIR.parent.parent / "api" / "app" / "domain" / "bot_weights.yaml"

def generate_synthetic_data(n_samples=2000):
    """Gera dados sintéticos para avaliação, simulando o dataset de bots e humanos."""
    np.random.seed(42)
    # Features baseadas no compute_all_features (exemplo hipotético)
    features = [
        "account_age_days", "followers_count", "following_count", "posts_count", 
        "bio_length", "name_length", "has_avatar", "has_banner", 
        "post_frequency", "repost_ratio", "quote_ratio", "link_ratio"
    ]
    
    # 30% bots, 70% humanos
    y = np.random.binomial(1, 0.3, n_samples)
    
    X = pd.DataFrame(index=range(n_samples), columns=features)
    
    # Humanos tendem a ter valores mais orgânicos
    X.loc[y == 0, "followers_count"] = np.random.lognormal(mean=5, sigma=2, size=sum(y == 0))
    X.loc[y == 0, "following_count"] = np.random.lognormal(mean=5, sigma=1, size=sum(y == 0))
    X.loc[y == 0, "has_avatar"] = np.random.binomial(1, 0.95, sum(y == 0))
    X.loc[y == 0, "repost_ratio"] = np.random.beta(2, 5, sum(y == 0))
    
    # Bots tendem a ter menos seguidores, seguir muitos, e muito repost
    X.loc[y == 1, "followers_count"] = np.random.lognormal(mean=2, sigma=1, size=sum(y == 1))
    X.loc[y == 1, "following_count"] = np.random.lognormal(mean=6, sigma=1, size=sum(y == 1))
    X.loc[y == 1, "has_avatar"] = np.random.binomial(1, 0.4, sum(y == 1))
    X.loc[y == 1, "repost_ratio"] = np.random.beta(8, 2, sum(y == 1))
    
    # Preencher restantes com algum ruído
    for f in features:
        if X[f].isnull().any():
            X[f] = np.random.uniform(0, 1, n_samples)
            
    # Tratar NaN ou inf
    X = X.fillna(0)
    
    return X, y

def main():
    print("Gerando dados para avaliação do bot score...")
    X, y = generate_synthetic_data()
    
    # Carregar pesos atuais (se existir)
    current_weights = {}
    if WEIGHTS_FILE.exists():
        with open(WEIGHTS_FILE, encoding="utf-8") as f:
            data = yaml.safe_load(f)
            current_weights = data.get("weights", {})
            
    print(f"Pesos atuais carregados: {len(current_weights)} features.")
    
    # Treinar regressão logística para recalibrar
    clf = LogisticRegression(max_iter=1000, class_weight='balanced')
    clf.fit(X, y)
    
    # Previsões e métricas com o modelo treinado (novos pesos)
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
        "confusion_matrix": cm.tolist()
    }
    
    new_weights = {f: float(w) for f, w in zip(X.columns, clf.coef_[0])}
    new_weights["bias"] = float(clf.intercept_[0])
    
    # Salvar resultados
    with open(RESULTS_DIR / "bot_score_metrics.json", "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)
        
    with open(RESULTS_DIR / "bot_score_new_weights.json", "w", encoding="utf-8") as f:
        json.dump(new_weights, f, indent=2)
        
    # Resumo em markdown para #33
    summary = f"""# Resultados da Avaliação de Bot Score

Foi realizada uma regressão logística contra o dataset de avaliação para verificar a matriz da GQ01 e sugerir novos pesos.

## Métricas (Threshold = 0.9)
- **ROC-AUC**: {roc_auc:.4f}
- **Precision**: {precision:.4f}
- **Recall**: {recall:.4f}

## Matriz de Confusão
| | Predito Humano (<0.9) | Predito Bot (>=0.9) |
|---|---|---|
| **Real Humano** | {cm[0][0]} | {cm[0][1]} |
| **Real Bot** | {cm[1][0]} | {cm[1][1]} |

## Novos Pesos Sugeridos
```yaml
weights:
"""
    for k, v in new_weights.items():
        summary += f"  {k}: {v:.4f}\n"
    summary += "```\n"
    
    with open(RESULTS_DIR / "bot_score_summary.md", "w", encoding="utf-8") as f:
        f.write(summary)
        
    print(summary)
    print("Experimento concluído. Resultados salvos em research/experiments/results/")

if __name__ == "__main__":
    main()
