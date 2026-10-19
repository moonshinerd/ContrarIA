"""Guarda de autor-imprensa, órgão oficial e agência de checagem.

O bot ContrarIA nunca intervém em posts de veículos de imprensa, órgãos oficiais
ou agências de checagem, mesmo quando o veredito da alegação é adverso.
"""

import re
from collections.abc import Sequence

# Domínios oficiais, de checagem e jornalísticos conhecidos
OFFICIAL_DOMAINS: tuple[str, ...] = (
    ".jus.br",
    ".gov.br",
    ".leg.br",
    "tse.jus.br",
    "stf.jus.br",
    "camara.leg.br",
    "senado.leg.br",
    "planalto.gov.br",
)

FACTCHECK_DOMAINS: tuple[str, ...] = (
    "aosfatos.org",
    "lupa.uol.com.br",
    "agencialupa.org",
    "fatoouboato",
    "checamos.afp.com",
    "uol.com.br/confere",
    "estadao.com.br/estadao-verifica",
    "projetocomprova.com.br",
    "boatos.org",
)

JOURNALISTIC_DOMAINS: tuple[str, ...] = (
    "g1.globo.com",
    "folha.uol.com.br",
    "estadao.com.br",
    "uol.com.br",
    "oglobo.globo.com",
    "bbc.com",
    "cnnbrasil.com.br",
    "poder360.com.br",
    "cartacapital.com.br",
    "jota.info",
    "valor.globo.com",
    "metropoles.com",
    "teletime.com.br",
    "reuters.com",
    "elpais.com",
    "platobr.com.br",
    "brasil247.com",
    "capitalnews.com.br",
    "correiobraziliense.com.br",
)

# Heurística para display name: palavras inteiras que identificam imprensa ou órgão público
_PRESS_DISPLAY_NAME_REGEX = re.compile(
    r"\b("
    r"jornal(?:ismo|ista)?|not[ií]cias?|news|portal|ag[eê]ncia|r[aá]dio|tv|"
    r"folha|g1|estad[aã]o|o\s+globo|globo\s*news|poder\s*360|"
    r"correio\s+braziliense|capital\s+news|brasil\s*247|carta\s*capital|"
    r"metr[oó]poles|uol|bbc|reuters|aos\s+fatos|lupa|"
    r"tse|stf|c[aâ]mara|senado|planalto"
    r")\b",
    re.IGNORECASE,
)

DEFAULT_PRESS_HANDLES: tuple[str, ...] = (
    "poder360.bsky.social",
    "folha",
    "estadao",
    "g1",
    "oglobo",
    "cnnbrasil",
    "correiocb.bsky.social",
    "capitalnews.bsky.social",
    "brasil247",
    "cartacapital",
    "metropoles",
    "uol",
    "bbc",
    "reuters",
    "aosfatos",
    "lupa",
    "g1-bot-rss.adilson.net.br",
    "tse",
    "stf",
    "camara",
    "senado",
    "planalto",
    "poder360",
    "correiocb",
    "capitalnews",
)


def is_press_or_official_author(
    handle: str | None = None,
    display_name: str | None = None,
    did: str | None = None,
    settings: object | None = None,
    *,
    press_handles: Sequence[str] | None = None,
) -> bool:
    """Verifica se o autor é veículo de imprensa, órgão oficial ou agência de checagem.

    Função pura que avalia:
    1. Se o handle está na lista configurável (exato, prefixo de domínio ou subdomínio).
    2. Se o handle termina em domínio jornalístico, oficial (.gov.br, etc.) ou de checagem.
    3. Se o display_name contém palavras inteiras que indicam imprensa ou órgão público.
    """
    if press_handles is None:
        if settings is not None and hasattr(settings, "press_account_handles"):
            press_handles = settings.press_account_handles
        else:
            try:
                from app.core.config import get_settings

                cfg = get_settings()
                press_handles = cfg.press_account_handles
            except Exception:
                press_handles = DEFAULT_PRESS_HANDLES

    if handle and isinstance(handle, str):
        h = handle.strip().lower().lstrip("@")
        if h:
            # 1. Checa a lista configurável de handles/prefixos
            for target in press_handles:
                t = target.strip().lower().lstrip("@")
                if not t:
                    continue
                if h == t:
                    return True
                if "." in t:
                    if h.endswith("." + t):
                        return True
                else:
                    if h.split(".")[0] == t or h.startswith(t + "."):
                        return True

            # 2. Checa domínios oficiais, checadores e jornalísticos
            all_domains = OFFICIAL_DOMAINS + FACTCHECK_DOMAINS + JOURNALISTIC_DOMAINS
            for dom in all_domains:
                dom_host = dom.strip().lower().split("/")[0]
                if dom_host.startswith("."):
                    if h.endswith(dom_host):
                        return True
                else:
                    if h == dom_host or h.endswith("." + dom_host):
                        return True

    # 3. Checa heurística de palavras inteiras no nome de exibição
    if display_name and isinstance(display_name, str):
        if _PRESS_DISPLAY_NAME_REGEX.search(display_name):
            return True

    # 4. Checa did contra a lista configurada, se houver
    if did and isinstance(did, str):
        d = did.strip().lower()
        for target in press_handles:
            if d == target.strip().lower():
                return True

    return False
