"""Testes dos endpoints administrativos e ferramentas de logs."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, get_settings
from app.db.base import Base
from app.db.orm import Post, SystemLog
from app.main import app
from app.routers.v1.admin import get_db
from app.scripts.backfill_logs import parse_log_line

test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
Base.metadata.create_all(bind=test_engine)


def override_get_db():
    with Session(test_engine) as session:
        yield session


def get_test_settings(admin_key: str = "secret-test-key") -> Settings:
    settings = get_settings()
    settings.admin_api_key = admin_key
    return settings


app.dependency_overrides[get_db] = override_get_db
app.dependency_overrides[get_settings] = lambda: get_test_settings("secret-test-key")

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    app.dependency_overrides[get_settings] = lambda: get_test_settings("secret-test-key")
    yield


def test_admin_auth_fails_when_unconfigured():
    app.dependency_overrides[get_settings] = lambda: get_test_settings(admin_key="")
    response = client.get("/v1/admin/overview")
    assert response.status_code == 503
    assert "não configurada" in response.json()["detail"]


def test_admin_auth_fails_when_missing_key():
    response = client.get("/v1/admin/overview")
    assert response.status_code == 401
    assert "Autenticação necessária" in response.json()["detail"]


def test_admin_auth_fails_with_invalid_key():
    response = client.get("/v1/admin/overview", headers={"X-Admin-Api-Key": "wrong-key"})
    assert response.status_code == 401
    assert "inválida" in response.json()["detail"]


def test_admin_auth_succeeds_with_header():
    response = client.get("/v1/admin/overview", headers={"X-Admin-Api-Key": "secret-test-key"})
    assert response.status_code == 200
    data = response.json()
    assert "posts" in data
    assert "llm_usage" in data


def test_admin_auth_succeeds_with_bearer():
    response = client.get("/admin/overview", headers={"Authorization": "Bearer secret-test-key"})
    assert response.status_code == 200
    data = response.json()
    assert "posts" in data


def test_admin_logs_filtering_and_pagination():
    headers = {"X-Admin-Api-Key": "secret-test-key"}

    with Session(test_engine) as session:
        now = datetime.now(UTC)
        session.add_all(
            [
                SystemLog(
                    created_at=now - timedelta(minutes=5),
                    level="INFO",
                    logger="contraria.worker",
                    service="worker",
                    message="Processando post 1",
                    context={"post_id": 1},
                ),
                SystemLog(
                    created_at=now - timedelta(minutes=4),
                    level="ERROR",
                    logger="contraria.pipeline",
                    service="worker",
                    message="Falha de rede ao consultar fonte",
                    context={"error": "timeout"},
                ),
                SystemLog(
                    created_at=now - timedelta(minutes=2),
                    level="INFO",
                    logger="contraria.api",
                    service="api",
                    message="Consulta recebida na API",
                ),
            ]
        )
        session.commit()

    # Listar todos
    res = client.get("/v1/admin/logs", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 3
    assert len(data["items"]) == 3

    # Filtrar por nível ERROR
    res_err = client.get("/v1/admin/logs?level=ERROR", headers=headers)
    assert res_err.status_code == 200
    data_err = res_err.json()
    assert data_err["total"] == 1
    assert data_err["items"][0]["level"] == "ERROR"

    # Filtrar por serviço api
    res_api = client.get("/v1/admin/logs?service=api", headers=headers)
    assert res_api.status_code == 200
    data_api = res_api.json()
    assert data_api["total"] == 1
    assert data_api["items"][0]["service"] == "api"

    # Busca textual
    res_search = client.get("/v1/admin/logs?search=rede", headers=headers)
    assert res_search.status_code == 200
    assert res_search.json()["total"] == 1


def test_admin_db_tables_and_records():
    headers = {"X-Admin-Api-Key": "secret-test-key"}

    with Session(test_engine) as session:
        session.add(
            Post(
                uri="at://did:plc:123/app.bsky.feed.post/1",
                cid="cid1",
                author_did="did:plc:123",
                text="Post de teste",
                source="search",
                triage_status="pending",
                created_at=datetime.now(UTC),
            )
        )
        session.commit()

    # Listar tabelas
    res_tables = client.get("/v1/admin/db/tables", headers=headers)
    assert res_tables.status_code == 200
    tables = {item["table_name"]: item["total_rows"] for item in res_tables.json()}
    assert "posts" in tables
    assert tables["posts"] == 1

    # Obter dados da tabela posts
    res_data = client.get("/v1/admin/db/tables/posts", headers=headers)
    assert res_data.status_code == 200
    data = res_data.json()
    assert data["total_rows"] == 1
    assert len(data["rows"]) == 1
    assert data["rows"][0]["text"] == "Post de teste"

    # Tabela inexistente ou bloqueada
    res_invalid = client.get("/v1/admin/db/tables/nao_existe", headers=headers)
    assert res_invalid.status_code == 404


def test_admin_db_query_select_allowed():
    headers = {"X-Admin-Api-Key": "secret-test-key"}

    with Session(test_engine) as session:
        session.add(
            Post(
                uri="at://did:plc:abc/app.bsky.feed.post/999",
                cid="cid999",
                author_did="did:plc:abc",
                text="Post para consulta SQL",
                source="jetstream",
                triage_status="processed",
                created_at=datetime.now(UTC),
            )
        )
        session.commit()

    query_body = {
        "query": "SELECT uri, triage_status, text FROM posts WHERE triage_status = 'processed'",
        "limit": 10,
    }
    res = client.post("/v1/admin/db/query", json=query_body, headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["columns"] == ["uri", "triage_status", "text"]
    assert len(data["rows"]) == 1
    assert data["rows"][0][1] == "processed"


def test_admin_db_query_blocks_modifications():
    headers = {"X-Admin-Api-Key": "secret-test-key"}

    # Tentativa de DROP
    res_drop = client.post(
        "/v1/admin/db/query", json={"query": "DROP TABLE posts"}, headers=headers
    )
    assert res_drop.status_code == 400
    assert "Apenas instruções SELECT ou WITH" in res_drop.json()["detail"]

    # Tentativa de DELETE
    res_del = client.post(
        "/v1/admin/db/query", json={"query": "DELETE FROM posts WHERE id = 1"}, headers=headers
    )
    assert res_del.status_code == 400

    # Tentativa de INSERT disfarçado ou concatenado
    res_multi = client.post(
        "/v1/admin/db/query",
        json={"query": "SELECT * FROM posts; INSERT INTO posts (uri) VALUES ('hack')"},
        headers=headers,
    )
    assert res_multi.status_code == 400
    assert "ponto-e-vírgula" in res_multi.json()["detail"]


def test_backfill_log_parser():
    # 1. JSON puro da aplicação
    app_json = (
        '{"ts": "2026-10-06T12:00:00Z", "level": "WARNING", '
        '"logger": "contraria.worker", "msg": "Teto atingido", "queue_len": 100}'
    )
    parsed1 = parse_log_line(app_json, default_service="worker")
    assert parsed1 is not None
    assert parsed1["level"] == "WARNING"
    assert parsed1["logger"] == "contraria.worker"
    assert parsed1["message"] == "Teto atingido"
    assert parsed1["context"] == {"queue_len": 100}

    # 2. JSON do docker encapsulando log do app
    docker_json = (
        '{"log": "{\\"ts\\": \\"2026-10-06T12:05:00Z\\", \\"level\\": \\"ERROR\\", '
        '\\"logger\\": \\"contraria.pipeline\\", \\"msg\\": \\"Falha Jev\\"}\\n", '
        '"stream": "stdout", "time": "2026-10-06T12:05:01Z"}'
    )
    parsed2 = parse_log_line(docker_json, default_service="worker")
    assert parsed2 is not None
    assert parsed2["level"] == "ERROR"
    assert parsed2["message"] == "Falha Jev"

    # 3. Linha de texto convencional
    text_line = "2026-10-06 12:10:00 [INFO] contraria.worker: Ciclo concluído com sucesso"
    parsed3 = parse_log_line(text_line, default_service="worker")
    assert parsed3 is not None
    assert parsed3["level"] == "INFO"
    assert parsed3["logger"] == "contraria.worker"
    assert parsed3["message"] == "Ciclo concluído com sucesso"


def test_database_log_handler_saves_to_db(tmp_path):
    import logging

    from app.core.db_logging import DatabaseLogHandler

    db_file = tmp_path / "test_logging.db"
    db_url = f"sqlite:///{db_file}"
    engine = create_engine(db_url)
    Base.metadata.create_all(bind=engine)

    handler = DatabaseLogHandler(
        database_url=db_url,
        service_name="test-service",
        batch_size=1,
        flush_interval_seconds=0.1,
    )

    test_logger = logging.getLogger("test.logger.direct")
    test_logger.setLevel(logging.INFO)
    test_logger.addHandler(handler)

    try:
        test_logger.info("Mensagem de teste para o banco", extra={"campo_extra": "valor123"})
        # Aguarda flush do worker loop
        handler.close()

        with Session(engine) as session:
            logs = session.query(SystemLog).all()
            assert len(logs) == 1
            assert logs[0].message == "Mensagem de teste para o banco"
            assert logs[0].service == "test-service"
            assert logs[0].context == {"campo_extra": "valor123"}
    finally:
        test_logger.removeHandler(handler)
        engine.dispose()
