"""Pool de análises simultâneas do worker.

Cada análise passa a maior parte do tempo esperando rede (fontes de evidência, matérias,
Bluesky). Rodar várias ao mesmo tempo aproveita essa espera; o limite é a CPU do Jev e as
cotas das APIs. `concurrency` é configurável (`WORKER_PIPELINE_CONCURRENCY`).
"""

import asyncio
import logging

logger = logging.getLogger("contraria.services.analysis_pool")


class AnalysisPool:
    def __init__(
        self, posts, pipeline, *, concurrency: int, tick_seconds: float, max_attempts: int
    ):
        self.posts = posts
        self.pipeline = pipeline
        self.concurrency = concurrency
        self.tick_seconds = tick_seconds
        self.max_attempts = max_attempts
        self.in_flight: dict[str, asyncio.Task] = {}
        self._attempts: dict[str, int] = {}

    async def _process(self, post) -> None:
        try:
            decision = await self.pipeline.analyze(post)
            status = "ignored" if decision.action == "IGNORE" else "processed"
            self.posts.update_triage(post.uri, status=status, priority=0.0)
            self._attempts.pop(post.uri, None)
        except Exception:
            logger.exception("Falha no pipeline GQ01 para %s", post.uri)
            self.pipeline.db.rollback()
            attempts = self._attempts.get(post.uri, 0) + 1
            self._attempts[post.uri] = attempts
            if attempts >= self.max_attempts:
                # Post que sempre falha não pode travar uma vaga da fila para sempre.
                logger.error("Post %s removido da fila após %d falhas", post.uri, attempts)
                self.posts.update_triage(post.uri, status="ignored", priority=0.0)
                self._attempts.pop(post.uri, None)

    def _launch(self) -> None:
        free = self.concurrency - len(self.in_flight)
        if free <= 0:
            return
        candidates = self.posts.get_triage_candidates(free, exclude_uris=set(self.in_flight))
        for post, _relevance in candidates:
            self.in_flight[post.uri] = asyncio.create_task(self._process(post))

    async def step(self) -> None:
        """Completa vagas livres e espera a próxima análise terminar (ou o tick)."""
        self._launch()
        if not self.in_flight:
            await asyncio.sleep(self.tick_seconds)
            return
        done, _ = await asyncio.wait(
            set(self.in_flight.values()),
            timeout=self.tick_seconds,
            return_when=asyncio.FIRST_COMPLETED,
        )
        for uri in [u for u, t in self.in_flight.items() if t in done]:
            del self.in_flight[uri]

    def cancel(self) -> None:
        for task in self.in_flight.values():
            task.cancel()
