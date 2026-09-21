"""Mapeamentos ORM do ContrarIA."""

from app.db.orm.fact_article import FactArticle
from app.db.orm.llm_usage import LLMUsage

__all__ = ["FactArticle", "LLMUsage"]
