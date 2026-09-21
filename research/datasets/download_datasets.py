"""Script idempotente para download e pré-processamento dos datasets de Fake News em PT-BR.

Datasets integrados:
1. Fake.br Corpus (GitHub roneysco/Fake.br-Corpus) - 7.200 notícias alinhadas
2. FakeRecogna (Hugging Face recogna-nlp/FakeRecogna) - 11.902 notícias com categoria e títulos

Os dados brutos e unificados são salvos em `research/datasets/data/`, ignorados pelo Git.
"""

import argparse
from pathlib import Path
import sys
import urllib.request
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent / "data"

FAKE_BR_URL = "https://raw.githubusercontent.com/roneysco/Fake.br-Corpus/master/preprocessed/pre-processed.csv"
FAKE_RECOGNA_URL = (
    "https://huggingface.co/datasets/recogna-nlp/FakeRecogna/resolve/main/FakeRecogna.csv"
)


def download_file(url: str, dest_path: Path, force: bool = False) -> None:
    """Baixa um arquivo apenas se não existir ou se force=True."""
    if dest_path.exists() and not force and dest_path.stat().st_size > 0:
        print(f"[OK] Já existe: {dest_path.name} ({dest_path.stat().st_size / 1024 / 1024:.2f} MB)")
        return

    print(f"[*] Baixando {dest_path.name} de {url}...")
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    import subprocess
    # No macOS, curl utiliza o keychain nativo com certificados confiaveis
    cmd = ["curl", "-sSL", "-A", "ContrarIA-Research/1.0", "-o", str(dest_path), url]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0 or not dest_path.exists() or dest_path.stat().st_size == 0:
        raise RuntimeError(f"Falha ao baixar {url} com curl: {res.stderr}")

    print(f"[CONCLUÍDO] Salvo em {dest_path.name} ({dest_path.stat().st_size / 1024 / 1024:.2f} MB)")


def load_and_standardize_fake_br(csv_path: Path) -> pd.DataFrame:
    """Padroniza o Fake.br Corpus."""
    print("[*] Processando Fake.br Corpus...")
    df = pd.read_csv(csv_path)
    # Colunas: index, label, preprocessed_news
    # label: 'fake' ou 'true'
    processed = pd.DataFrame(
        {
            "text": df["preprocessed_news"].fillna("").astype(str),
            "title": "",
            "label": (df["label"].str.lower().str.strip() == "fake").astype(int),
            "source": "fake_br",
            "category": "geral",
        }
    )
    processed = processed[processed["text"].str.strip().str.len() > 10]
    print(f"    Total Fake.br válidos: {len(processed)} (Fake: {processed['label'].sum()})")
    return processed


def load_and_standardize_fake_recogna(csv_path: Path) -> pd.DataFrame:
    """Padroniza o FakeRecogna (0.0 = Fake [boatos.org, e-farsas], 1.0 = Real [uol, g1])."""
    print("[*] Processando FakeRecogna...")
    df = pd.read_csv(csv_path)
    # Colunas: Titulo, Subtitulo, Noticia, Categoria, Data, Autor, URL, Classe
    # 0 = Fake -> rotulo 1; 1 = Real -> rotulo 0
    is_fake = (pd.to_numeric(df["Classe"], errors="coerce") == 0).astype(int)

    titles = df["Titulo"].fillna("").astype(str).str.strip()
    bodies = df["Noticia"].fillna("").astype(str).str.strip()
    categories = df["Categoria"].fillna("geral").astype(str).str.lower().str.strip()

    texts = titles + ". " + bodies

    processed = pd.DataFrame(
        {
            "text": texts,
            "title": titles,
            "label": is_fake,
            "source": "fake_recogna",
            "category": categories,
        }
    )
    processed = processed[processed["text"].str.strip().str.len() > 10]
    print(f"    Total FakeRecogna válidos: {len(processed)} (Fake: {processed['label'].sum()})")
    return processed


def main() -> None:
    parser = argparse.ArgumentParser(description="Download e preparação dos datasets de Fake News.")
    parser.add_argument("--force", action="store_true", help="Força novo download mesmo se o arquivo já existir.")
    args = parser.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    fake_br_file = DATA_DIR / "fake_br.csv"
    fake_recogna_file = DATA_DIR / "fake_recogna.csv"
    output_unified = DATA_DIR / "unified_dataset.csv"

    try:
        download_file(FAKE_BR_URL, fake_br_file, force=args.force)
        download_file(FAKE_RECOGNA_URL, fake_recogna_file, force=args.force)
    except Exception as e:
        print(f"[ERRO] Falha ao baixar datasets: {e}", file=sys.stderr)
        sys.exit(1)

    df_br = load_and_standardize_fake_br(fake_br_file)
    df_rec = load_and_standardize_fake_recogna(fake_recogna_file)

    unified = pd.concat([df_br, df_rec], ignore_index=True)
    unified.to_csv(output_unified, index=False)
    print(f"\n[SUCESSO] Dataset unificado salvo em {output_unified}")
    print(f"          Total de amostras: {len(unified)}")
    print(f"          Distribuição: {unified['label'].value_counts().to_dict()} (1=Fake, 0=Real)")


if __name__ == "__main__":
    main()
