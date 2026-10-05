"""Gera `app/domain/data/municipios_br.json` a partir da API de localidades do IBGE.

    docker compose run --rm --no-deps -v "$PWD/api/app:/srv/app" api \
        python -m app.scripts.build_gazetteer

Fonte: https://servicodados.ibge.gov.br/api/v1/localidades/municipios (dados abertos do IBGE).
O arquivo é um dicionário {UF: [municípios]} usado por `app/domain/geo.py`.
"""

import json
from pathlib import Path

import httpx

URL = "https://servicodados.ibge.gov.br/api/v1/localidades/municipios"
OUTPUT = Path(__file__).resolve().parents[1] / "domain" / "data" / "municipios_br.json"


def uf_of(municipio: dict) -> str:
    micro = municipio.get("microrregiao") or {}
    uf = (micro.get("mesorregiao") or {}).get("UF")
    if not uf:
        immediate = municipio.get("regiao-imediata") or {}
        uf = (immediate.get("regiao-intermediaria") or {}).get("UF")
    return uf["sigla"]


def main() -> None:
    response = httpx.get(URL, timeout=60, follow_redirects=True)
    response.raise_for_status()
    municipios = response.json()
    by_uf: dict[str, list[str]] = {}
    for municipio in municipios:
        by_uf.setdefault(uf_of(municipio), []).append(municipio["nome"])
    for names in by_uf.values():
        names.sort()
    OUTPUT.write_text(
        json.dumps(dict(sorted(by_uf.items())), ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"{sum(len(v) for v in by_uf.values())} municípios em {len(by_uf)} UFs -> {OUTPUT}")


if __name__ == "__main__":
    main()
