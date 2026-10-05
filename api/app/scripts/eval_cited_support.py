"""Avalia se o NLI por trechos separa "post fiel à matéria que cita" de variantes adulteradas.

Para cada post da família "Resultado das eleições 2026 em <cidade> (<UF>): votação para
presidente no <escola>, na <N>ª zona eleitoral" (manchetes do G1), lê a matéria linkada e mede o
maior entailment
entre a alegação e os trechos (título + janelas de 2 frases), como no SummaC/AlignScore. Compara o
post original (positivo) com três adulterações (negativos): outra escola, outra zona e outra cidade.

    docker compose run --rm --no-deps -e PYTHONPATH=/srv -v "$PWD/api/app:/srv/app" api \
        python -m app.scripts.eval_cited_support --posts 36

Mostra recall e falsos aceites por limiar; o padrão de `CITED_SOURCE_ENTAILMENT_MIN` vem daqui.
"""

import argparse
import asyncio
import random
import re
import statistics

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.clients.bluesky_client import BlueskyClient
from app.core.config import get_settings
from app.db.orm.posts import Post as PostRow
from app.models.classifiers.jev import get_jev_classifier
from app.services.jev_verification import _fetch_article_text, _nli_chunks, _title_from_url

PATTERN = re.compile(
    r"Resultado das eleições 2026 em (.+?) \((\w\w)\): votação para presidente "
    r"(?:no|na) (.+?), na (\d+)ª zona eleitoral"
)


def variants(text: str, others: list[str]) -> dict[str, str]:
    match = PATTERN.match(text)
    if not match:
        return {}
    city, uf, school, zone = match.groups()
    other = PATTERN.match(random.Random(len(text)).choice(others))
    out = {"outra_zona": text.replace(f"{zone}ª zona", f"{int(zone) + 7}ª zona")}
    if other and other.group(3) != school:
        out["outra_escola"] = text.replace(school, other.group(3))
    if other and other.group(1) != city:
        out["outra_cidade"] = text.replace(f"{city} ({uf})", f"{other.group(1)} ({other.group(2)})")
    return out


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--posts", type=int, default=36)
    args = parser.parse_args()
    settings = get_settings()
    engine = create_engine(settings.database_url)
    with Session(engine) as session:
        rows = session.scalars(
            select(PostRow)
            .where(PostRow.text.ilike("Resultado das eleições 2026 em%votação para presidente%"))
            .limit(500)
        ).all()
    random.Random(1).shuffle(rows)
    client, classifier = BlueskyClient(settings), get_jev_classifier(settings)
    hydrated = {p.uri: p for p in await client.get_posts([r.uri for r in rows[: args.posts]])}
    items = []
    for row in rows[: args.posts]:
        post = hydrated.get(row.uri)
        article = await _fetch_article_text(post.links[0]) if post and post.links else None
        if article:
            items.append((row.text, _title_from_url(post.links[0]), article))
    print(f"{len(items)} posts com matéria lida")
    others = [i[0] for i in items]
    scores: dict[str, list[float]] = {}
    for text, title, article in items:
        chunks = _nli_chunks(title, article)
        for name, claim in {"positivo": text, **variants(text, others)}.items():
            results = await classifier.predict_nli_batch([(c, claim) for c in chunks])
            scores.setdefault(name, []).append(max(r["entailment"] for r in results))
    for name, values in scores.items():
        mean, low = statistics.mean(values), min(values)
        print(f"{name:13s} n={len(values):2d} média {mean:.2f} mín {low:.2f}")
    for threshold in (0.5, 0.7, 0.8, 0.9):
        recall = sum(v >= threshold for v in scores["positivo"]) / len(scores["positivo"])
        accepted = ", ".join(
            f"{k}={sum(v >= threshold for v in vals) / len(vals):.2f}"
            for k, vals in scores.items()
            if k != "positivo"
        )
        print(f"limiar {threshold}: recall={recall:.2f} | falsos aceites: {accepted}")


if __name__ == "__main__":
    asyncio.run(main())
