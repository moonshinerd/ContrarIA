"""Mede o throughput da verificação (Jev) com diferentes níveis de concorrência.

Só chama `JevVerificationService.verify`: não grava decisão, não enfileira intervenção
e não publica nada. Cada nível usa um conjunto próprio de posts (sem repetição) e uma
instância nova do serviço, para que o cache de evidências de um nível não beneficie o seguinte.

    docker compose run --rm --no-deps api python -m app.scripts.benchmark_concurrency \
        --levels 1,3,6,10 --posts 20
"""

import argparse
import asyncio
import json
import statistics
import time

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.orm.posts import Post as PostRow
from app.domain.entities import Post
from app.services.jev_verification import JevVerificationService


def sample_posts(engine, total: int, by_priority: bool = False) -> list[Post]:
    with Session(engine) as session:
        rows = session.scalars(
            select(PostRow)
            .where(PostRow.triage_status.in_(["monitor", "queued"]))
            .order_by(
                PostRow.priority.desc().nullslast() if by_priority else PostRow.first_seen_at.desc()
            )
            .limit(total if by_priority else total * 20)
        ).all()
    if not by_priority:
        import random

        random.Random(42).shuffle(rows)
    return [
        Post(
            uri=r.uri,
            cid=r.cid,
            author_did=r.author_did,
            text=r.text,
            created_at=r.created_at,
            langs=r.langs or [],
        )
        for r in rows[:total]
    ]


async def run_level(service: JevVerificationService, posts: list[Post], concurrency: int) -> dict:
    semaphore = asyncio.Semaphore(concurrency)
    latencies: list[float] = []
    labels: dict[str, int] = {}
    errors = 0

    async def one(post: Post) -> None:
        nonlocal errors
        async with semaphore:
            started = time.monotonic()
            try:
                verdict = await service.verify(post)
                labels[verdict.label.value] = labels.get(verdict.label.value, 0) + 1
            except Exception:
                errors += 1
            latencies.append(time.monotonic() - started)

    started = time.monotonic()
    await asyncio.gather(*(one(p) for p in posts))
    wall = time.monotonic() - started
    ordered = sorted(latencies)
    return {
        "concurrency": concurrency,
        "posts": len(posts),
        "wall_s": round(wall, 1),
        "posts_per_min": round(len(posts) / wall * 60, 2),
        "latency_p50_s": round(statistics.median(ordered), 1),
        "latency_p95_s": round(ordered[max(0, int(len(ordered) * 0.95) - 1)], 1),
        "errors": errors,
        "labels": labels,
    }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--levels", default="1,3,6,10")
    parser.add_argument("--posts", type=int, default=20, help="posts por nível")
    parser.add_argument(
        "--top",
        action="store_true",
        help="amostra os de maior prioridade (o que o worker realmente processa)",
    )
    args = parser.parse_args()
    levels = [int(x) for x in args.levels.split(",")]

    settings = get_settings()
    engine = create_engine(settings.database_url)
    posts = sample_posts(engine, args.posts * len(levels), by_priority=args.top)
    if len(posts) < args.posts * len(levels):
        raise SystemExit(f"Só {len(posts)} posts disponíveis na fila para amostrar")

    for i, level in enumerate(levels):
        service = JevVerificationService.from_settings(settings=settings, engine=engine)
        chunk = posts[i * args.posts : (i + 1) * args.posts]
        print(json.dumps(await run_level(service, chunk, level), ensure_ascii=False), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
