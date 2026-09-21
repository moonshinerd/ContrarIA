"""Smoke test contra o Bluesky real (issue #10).

    python -m app.scripts.bsky_smoke --actor bsky.app --query "urna eletrônica"

Leituras públicas sempre rodam; a busca autenticada só roda se houver
BLUESKY_HANDLE/BLUESKY_APP_PASSWORD no .env (ou sessão já persistida).
"""

import argparse
import asyncio

from app.clients.bluesky_client import BlueskyAuthError, BlueskyClient


async def main(actor: str, query: str) -> None:
    client = BlueskyClient()
    try:
        account = await client.get_profile(actor)
        print(
            f"[perfil] @{account.handle} did={account.did} "
            f"seguidores={account.followers_count} seguindo={account.follows_count} "
            f"posts={account.posts_count} criado={account.created_at} "
            f"self_labels={account.self_labels}"
        )
        feed = await client.get_author_feed(actor, limit=5)
        print(f"[feed] {len(feed)} itens; reposts={sum(p.is_repost for p in feed)}")
        if feed:
            hydrated = await client.get_posts([p.uri for p in feed])
            likes = [p.like_count for p in hydrated]
            print(f"[getPosts] {len(hydrated)} posts hidratados; curtidas={likes}")
        try:
            results = await client.search_posts(query, sort="top", limit=5)
        except BlueskyAuthError as exc:
            print(f"[busca] pulada: {exc}")
            return
        print(f"[busca] {len(results)} resultados para {query!r}")
        for post in results:
            stats = f"♥{post.like_count} ↻{post.repost_count}"
            print(f"  - @{post.author_handle} {stats}: {post.text[:80]!r}")
    finally:
        await client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--actor", default="bsky.app")
    parser.add_argument("--query", default="urna eletrônica")
    args = parser.parse_args()
    asyncio.run(main(args.actor, args.query))
