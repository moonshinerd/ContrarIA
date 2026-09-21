"""Configura a conta do bot (issue #10): login + self-label `bot` no perfil.

    python -m app.scripts.bsky_bot_setup

Idempotente: se o self-label já existir, não altera nada.
"""

import asyncio

from app.clients.bluesky_client import BlueskyClient


async def main() -> None:
    client = BlueskyClient()
    try:
        did = await client.login()
        changed = await client.ensure_bot_self_label()
        account = await client.get_profile(did)
        print(f"@{account.handle} ({did}) self_labels={account.self_labels} alterado={changed}")
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
