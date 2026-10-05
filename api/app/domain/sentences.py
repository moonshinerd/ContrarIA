"""Divisão de texto em frases, com tratamento de abreviações do português.

Bibliotecas prontas não resolvem o português aqui: o pySBD não tem o idioma e o sentencex
(Wikimedia) ainda corta em "Min." e "E.E.I.E.F.". A regra segue o que Punkt e pySBD fazem, com a
lista de abreviações do jornalismo brasileiro: não há fronteira depois de abreviação, de sigla de
uma letra
("E. M."), de sequência de iniciais ("E.E.I.E.F.") nem quando o que vem depois começa em minúscula
("5 de out. de 2026"). Perde-se "Plano B. Depois" (sigla de uma letra no fim de frase), uma troca
aceita: cortar um nome próprio no meio é o erro mais caro para a verificação.
"""

import re

_ABBREVIATIONS = frozenset(
    "dr dra drs sr sra srs srta prof profa profs dep sen gov vice pres min des cel gen cap ten sgt "
    "brig alm mal av al ed fl fls pag pags art arts etc ex obs tel vs cf apud op cit sec".split()
)
_BOUNDARY = re.compile(r"[.!?]+(?=\s)\s+")
_INITIALS = re.compile(r"^(?:[^\W\d_]\.)+[^\W\d_]?$")
_OPENERS = "\"'“‘(«[@#"


def _last_token(prefix: str) -> str:
    parts = prefix.split()
    return parts[-1] if parts else ""


def _is_boundary(text: str, match: re.Match[str]) -> bool:
    following = text[match.end() : match.end() + 1]
    if not following or not (following.isupper() or following.isdigit() or following in _OPENERS):
        return False
    if match.group().strip() != ".":
        return True  # "!", "?" e reticências encerram a frase
    token = _last_token(text[: match.start() + 1])
    word = token.rstrip(".")
    if word.casefold() in _ABBREVIATIONS:
        return False
    return not (_INITIALS.match(token) or (len(word) == 1 and word.isalpha()))


def split_sentences(text: str) -> list[str]:
    """Quebra o texto em frases sem cortar abreviações nem nomes com iniciais."""
    sentences: list[str] = []
    start = 0
    for match in _BOUNDARY.finditer(text):
        if _is_boundary(text, match):
            sentences.append(text[start : match.start() + len(match.group().rstrip())])
            start = match.end()
    sentences.append(text[start:])
    return [s.strip() for s in sentences if s.strip()]
