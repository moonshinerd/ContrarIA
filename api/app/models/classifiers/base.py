"""Porta para classificadores clássicos (ex.: pré-filtro de fake news)."""

from abc import ABC, abstractmethod


class TextClassifierPort(ABC):
    @abstractmethod
    def predict_proba(self, text: str) -> float:
        """Probabilidade [0, 1] de o texto pertencer à classe positiva."""
