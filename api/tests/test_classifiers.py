"""Testes unitários para o classificador clássico de fake news."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.models.classifiers.base import TextClassifierPort
from app.models.classifiers.fake_news_tfidf import FakeNewsTFIDFClassifier


class FakeTextClassifier(TextClassifierPort):
    """Fake classificador para uso em testes."""

    def __init__(self, proba: float = 0.85) -> None:
        self.proba = proba
        self.calls: list[str] = []

    def predict_proba(self, text: str) -> float:
        self.calls.append(text)
        return self.proba


def test_fake_text_classifier():
    """Garante que FakeTextClassifier satisfaz a porta e registra chamadas."""
    classifier = FakeTextClassifier(proba=0.92)
    assert isinstance(classifier, TextClassifierPort)

    score = classifier.predict_proba("Texto de teste para classificação")
    assert score == 0.92
    assert len(classifier.calls) == 1
    assert classifier.calls[0] == "Texto de teste para classificação"


def test_tfidf_classifier_predict_proba_with_mock():
    """Testa predição de probabilidade com modelo mockado."""
    mock_pipeline = MagicMock()
    # Mock do predict_proba retornando [[p_real, p_fake]]
    mock_pipeline.predict_proba.return_value = [[0.15, 0.85]]

    clf = FakeNewsTFIDFClassifier(model=mock_pipeline)
    score = clf.predict_proba("Alegação suspeita de fraude")

    assert score == 0.85
    mock_pipeline.predict_proba.assert_called_once_with(["Alegação suspeita de fraude"])


def test_tfidf_classifier_empty_text():
    """Testa que texto vazio devolve 0.0 sem chamar o modelo."""
    mock_pipeline = MagicMock()
    clf = FakeNewsTFIDFClassifier(model=mock_pipeline)

    assert clf.predict_proba("") == 0.0
    assert clf.predict_proba("   ") == 0.0
    mock_pipeline.predict_proba.assert_not_called()


def test_tfidf_classifier_truncates_long_text():
    """Testa que textos longos são truncados em 300 caracteres para o Bluesky."""
    mock_pipeline = MagicMock()
    mock_pipeline.predict_proba.return_value = [[0.20, 0.80]]

    clf = FakeNewsTFIDFClassifier(model=mock_pipeline)
    texto_longo = "A" * 500
    clf.predict_proba(texto_longo)

    called_arg = mock_pipeline.predict_proba.call_args[0][0][0]
    assert len(called_arg) == 300


def test_tfidf_classifier_no_model_raises_runtime_error():
    """Testa erro quando nenhum modelo foi carregado."""
    clf = FakeNewsTFIDFClassifier(model=None, model_path=None)
    with pytest.raises(RuntimeError) as exc_info:
        clf.predict_proba("qualquer texto")
    assert "Nenhum modelo carregado" in str(exc_info.value)


def test_tfidf_classifier_missing_file_raises_filenotfound():
    """Testa que arquivo inexistente gera FileNotFoundError."""
    caminho_inexistente = Path("/tmp/modelo_inexistente_12345.joblib")
    with pytest.raises(FileNotFoundError):
        FakeNewsTFIDFClassifier(model_path=caminho_inexistente)
