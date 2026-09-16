"""Adapter do Bluesky (AT Protocol).

Implementado na issue do cliente Bluesky: login com sessão persistida
(createSession tem limite de 300/dia), getPosts/getProfile (AppView pública),
searchPosts (exige autenticação) e criação de quote posts.
"""

from app.domain.entities import Account, Post


class BlueskyClient:
    async def get_posts(self, uris: list[str]) -> list[Post]:
        raise NotImplementedError

    async def get_profile(self, actor: str) -> Account:
        raise NotImplementedError

    async def search_posts(self, query: str, *, lang: str = "pt", limit: int = 25) -> list[Post]:
        raise NotImplementedError

    async def quote_post(self, target: Post, text: str) -> str:
        raise NotImplementedError
