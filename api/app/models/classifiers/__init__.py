"""Módulo de classificadores clássicos do ContrarIA."""

from app.models.classifiers.base import TextClassifierPort
from app.models.classifiers.fake_news_tfidf import FakeNewsTFIDFClassifier

__all__ = ["FakeNewsTFIDFClassifier", "TextClassifierPort"]
