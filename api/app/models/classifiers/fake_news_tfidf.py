"""Classificador TF-IDF para pré-filtro clássico de fake news.

Implementa TextClassifierPort carregando um modelo serializado (joblib)
treinado com datasets PT-BR (Fake.br e FakeRecogna).
"""

from pathlib import Path
from typing import Any

from app.models.classifiers.base import TextClassifierPort


class FakeNewsTFIDFClassifier(TextClassifierPort):
    """Adaptador de classificação de fake news via TF-IDF."""

    def __init__(self, model_path: str | Path | None = None, model: Any | None = None) -> None:
        self.model = model
        self.model_path = Path(model_path) if model_path else None

        if self.model is None and self.model_path is not None:
            self._load_model()

    def _load_model(self) -> None:
        if self.model_path is None or not self.model_path.exists():
            raise FileNotFoundError(f"Arquivo do modelo não encontrado em: {self.model_path}")
        try:
            import joblib
        except ImportError as e:
            raise RuntimeError(
                "joblib/scikit-learn não está instalado no ambiente da API. "
                "Instale joblib e scikit-learn para carregar o modelo pré-treinado."
            ) from e

        self.model = joblib.load(self.model_path)

    def predict_proba(self, text: str) -> float:
        """Retorna a probabilidade [0, 1] de o texto ser fake news (classe positiva)."""
        if not text or not text.strip():
            return 0.0

        if self.model is None:
            raise RuntimeError(
                "Nenhum modelo carregado no classificador. "
                "Forneça model_path ou um objeto de modelo."
            )

        # Trunca para 300 caracteres para compatibilidade com limite do Bluesky
        truncated = text.strip()[:300]
        probas = self.model.predict_proba([truncated])
        return float(probas[0][1])
