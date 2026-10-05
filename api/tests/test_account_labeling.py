from unittest.mock import AsyncMock

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.db.base import Base
from app.db.orm.bots import AccountAssessment
from app.domain.entities import Account
from app.services.account_labeling import BOT_LABEL, AccountLabelService


def make(enabled=True, applied=False, posts=100):
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    db = Session(engine)
    db.add(AccountAssessment(did="did:x", score=0.5, features={}, bot_label_applied=applied))
    db.commit()
    ozone = AsyncMock()
    settings = Settings(_env_file=None, pipeline_labeler_enabled=enabled)
    return (
        AccountLabelService(settings, db, ozone),
        ozone,
        db,
        Account(did="did:x", handle="x", posts_count=posts),
    )


def applied_flag(db):
    return db.scalar(select(AccountAssessment.bot_label_applied))


@pytest.mark.asyncio
async def test_rotula_conta_acima_do_limiar_e_marca_estado():
    service, ozone, db, account = make()
    assert await service.sync(account, 0.95) == "create"
    ozone.emit_label.assert_awaited_once_with(account, label_val=BOT_LABEL, action="create")
    assert applied_flag(db) is True
    # Segunda análise não emite de novo.
    assert await service.sync(account, 0.96) is None
    assert ozone.emit_label.await_count == 1


@pytest.mark.asyncio
async def test_nao_rotula_abaixo_do_limiar_nem_com_poucos_posts():
    service, ozone, db, account = make()
    assert await service.sync(account, 0.89) is None
    service2, ozone2, _, novo = make(posts=3)
    assert await service2.sync(novo, 0.99) is None
    ozone.emit_label.assert_not_awaited()
    ozone2.emit_label.assert_not_awaited()


@pytest.mark.asyncio
async def test_histerese_so_nega_bem_abaixo_do_limiar():
    service, ozone, db, account = make(applied=True)
    assert await service.sync(account, 0.85) is None  # entre 0,8 e 0,9: mantém
    assert applied_flag(db) is True
    assert await service.sync(account, 0.79) == "negate"
    ozone.emit_label.assert_awaited_once_with(account, label_val=BOT_LABEL, action="negate")
    assert applied_flag(db) is False


@pytest.mark.asyncio
async def test_falha_do_ozone_nao_muda_estado_nem_levanta():
    service, ozone, db, account = make()
    ozone.emit_label.side_effect = RuntimeError("ozone fora")
    assert await service.sync(account, 0.99) is None
    assert applied_flag(db) is False


@pytest.mark.asyncio
async def test_desligado_por_flag_nao_faz_nada():
    service, ozone, db, account = make(enabled=False)
    assert await service.sync(account, 0.99) is None
    ozone.emit_label.assert_not_awaited()
