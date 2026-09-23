"""Detecção do vazamento da checagem usada como rótulo."""

import re
import unicodedata
from urllib.parse import urlsplit, urlunsplit


def canonical_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    hostname = (parsed.hostname or "").casefold().removeprefix("www.")
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit((parsed.scheme.casefold(), hostname, path, "", ""))


def _normalized(value: str) -> str:
    text = unicodedata.normalize("NFKD", value.casefold())
    return " ".join("".join(char for char in text if not unicodedata.combining(char)).split())


def is_origin_evidence(
    *,
    evidence_url: str,
    title: str,
    snippet: str,
    origin_url: str,
    publisher: str,
) -> bool:
    evidence_canonical = canonical_url(evidence_url)
    origin_canonical = canonical_url(origin_url)
    if evidence_canonical and evidence_canonical == origin_canonical:
        return True

    evidence_host = urlsplit(evidence_canonical).hostname or ""
    origin_host = urlsplit(origin_canonical).hostname or ""
    if evidence_host and origin_host and evidence_host == origin_host:
        return True

    normalized_publisher = _normalized(publisher)
    if len(normalized_publisher) < 3:
        return False
    haystack = _normalized(f"{title} {snippet}")
    return bool(re.search(rf"\b{re.escape(normalized_publisher)}\b", haystack))
