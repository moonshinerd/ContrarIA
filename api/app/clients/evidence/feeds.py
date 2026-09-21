"""Feeds verificados de checagem de fatos; indisponíveis ficam sem URL padrão."""

FEEDS: dict[str, str | None] = {
    "lupa": "https://lupa.uol.com.br/feed",
    "aos_fatos": "https://www.aosfatos.org/noticias/feed/",
    "estadao_verifica": None,
    "g1_fato_fake": "https://g1.globo.com/rss/g1/fato-ou-fake/",
    "uol_confere": None,
    "boatos": "https://www.boatos.org/feed",
    "comprova": "https://projetocomprova.com.br/feed/",
    "tse": "https://www.tse.jus.br/comunicacao/noticias/RSS",
}
