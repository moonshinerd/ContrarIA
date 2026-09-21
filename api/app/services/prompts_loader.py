"""Carregador de prompts versionados.

Os prompts ficam armazenados em arquivos de texto sob `app/prompts/<nome>_v<N>.txt`.
Exemplo: `app/prompts/claim_extraction_v1.txt`.
"""

from functools import lru_cache
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def get_prompt_path(name: str, version: int = 1) -> Path:
    """Retorna o caminho do arquivo de prompt versionado."""
    return PROMPTS_DIR / f"{name}_v{version}.txt"


@lru_cache
def load_prompt(name: str, version: int = 1) -> str:
    """Lê e retorna o conteúdo do prompt versionado.

    Lança FileNotFoundError se o prompt com a versão informada não existir.
    """
    path = get_prompt_path(name, version)
    if not path.is_file():
        raise FileNotFoundError(f"Prompt '{name}' versão {version} não encontrado em {path}.")
    return path.read_text(encoding="utf-8").strip()
