import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.orm.posts import Post as PostRow
from app.domain.entities import Post
from app.jobs.collector import IngestGate
from app.repositories.posts import PostRepository
from app.services.analysis_pool import AnalysisPool


def domain_post(n: int) -> Post:
    return Post(
        uri=f"at://p{n}", cid="c", author_did="did:1", text="t", created_at=datetime.now(UTC)
    )


class FakeRepo:
    def __init__(self, n: int):
        self.queue = [domain_post(i) for i in range(n)]
        self.status: dict[str, str] = {}

    def get_triage_candidates(self, limit, *, exclude_uris=frozenset()):
        pending = [p for p in self.queue if p.uri not in self.status and p.uri not in exclude_uris]
        return [(p, 0.0) for p in pending[:limit]]

    def update_triage(self, uri, *, status, priority):
        self.status[uri] = status


class FakePipeline:
    def __init__(self, fail: set[str] = frozenset()):
        self.db = MagicMock()
        self.running = 0
        self.peak = 0
        self.fail = fail

    async def analyze(self, post):
        self.running += 1
        self.peak = max(self.peak, self.running)
        try:
            await asyncio.sleep(0.02)
            if post.uri in self.fail:
                raise RuntimeError("falha")
            return SimpleNamespace(action="MONITOR")
        finally:
            self.running -= 1


async def drain(pool: AnalysisPool, repo: FakeRepo) -> None:
    for _ in range(200):
        await pool.step()
        if len(repo.status) == len(repo.queue) and not pool.in_flight:
            return
    raise AssertionError("pool não terminou")


@pytest.mark.asyncio
async def test_respeita_o_limite_de_concorrencia_e_processa_tudo():
    repo, pipeline = FakeRepo(10), FakePipeline()
    pool = AnalysisPool(repo, pipeline, concurrency=3, tick_seconds=0.05, max_attempts=3)
    await drain(pool, repo)
    assert pipeline.peak == 3
    assert set(repo.status.values()) == {"processed"}


@pytest.mark.asyncio
async def test_post_que_sempre_falha_sai_da_fila_apos_as_tentativas():
    repo, pipeline = FakeRepo(3), FakePipeline(fail={"at://p1"})
    pool = AnalysisPool(repo, pipeline, concurrency=2, tick_seconds=0.05, max_attempts=2)
    await drain(pool, repo)
    assert repo.status["at://p1"] == "ignored"
    assert repo.status["at://p0"] == repo.status["at://p2"] == "processed"
    assert pipeline.db.rollback.call_count == 2


def make_repo():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    return PostRepository(engine), engine


def add_posts(engine, rows):
    with Session(engine) as session, session.begin():
        for uri, status, priority in rows:
            session.add(
                PostRow(
                    uri=uri,
                    cid="c",
                    author_did="d",
                    text="t",
                    created_at=datetime.now(UTC),
                    source="jetstream",
                    triage_status=status,
                    priority=priority,
                )
            )


def test_trim_mantem_os_de_maior_prioridade_e_expira_o_resto():
    repo, engine = make_repo()
    add_posts(
        engine,
        [
            ("a", "monitor", 5.0),
            ("b", "queued", 90.0),
            ("c", "monitor", 1.0),
            ("d", None, None),
            ("e", "processed", 99.0),
        ],
    )
    assert repo.pending_count() == 4  # processed não conta; sem triagem (NULL) conta
    assert repo.trim_pending(2) == 2
    assert repo.pending_count() == 2
    kept = {p.uri for p, _ in repo.get_triage_candidates(10)}
    assert kept == {"a", "b"}
    # exclude_uris tira os que já estão em análise
    assert {p.uri for p, _ in repo.get_triage_candidates(10, exclude_uris={"b"})} == {"a"}
    assert repo.existing_uris(["a", "e", "zzz"]) == {"a", "e"}


def test_gate_bloqueia_com_a_fila_cheia_e_libera_quando_ha_vaga():
    repo = MagicMock()
    repo.pending_count.return_value = 98
    gate = IngestGate(repo, max_pending=100, refresh_seconds=0)
    assert gate.room() == 2
    repo.pending_count.return_value = 100
    assert gate.room() == 0
    repo.pending_count.return_value = 40
    assert gate.room() == 60


def test_gate_desligado_com_teto_zero_nunca_bloqueia():
    assert IngestGate(MagicMock(), max_pending=0).room() > 1_000_000


def test_gate_soma_localmente_entre_leituras_do_banco():
    repo = MagicMock()
    repo.pending_count.return_value = 98
    gate = IngestGate(repo, max_pending=100, refresh_seconds=3600)
    assert gate.room() == 2
    gate.consume(2)
    assert gate.room() == 0
    assert repo.pending_count.call_count == 1


def test_gate_reserva_vagas_do_searchposts_fora_do_jetstream():
    repo = MagicMock()
    repo.pending_count.return_value = 70
    gate = IngestGate(repo, max_pending=100, refresh_seconds=0, search_reserve=30)
    assert gate.room(stream=True) == 0  # Jetstream para em 70
    assert gate.room() == 30  # searchPosts ainda tem as 30 vagas
