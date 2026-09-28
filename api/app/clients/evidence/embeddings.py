"""Modelo multilíngue local fixo: alterações exigem reindexar o acervo."""

from functools import lru_cache

MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
DIMENSIONS = 384


@lru_cache(maxsize=1)
def get_model():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(MODEL_NAME, device="cpu")


class LocalEmbedder:
    def encode(self, texts: list[str]) -> list[list[float]]:
        return (
            get_model()
            .encode(texts, normalize_embeddings=True, show_progress_bar=False, batch_size=32)
            .tolist()
        )
