"""Endpoints REST administrativos e de monitoramento (somente-leitura) do ContrarIA."""

import re
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Security, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import create_engine, func, text
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.orm import (
    AccountAssessment,
    CRCCalibrationRecord,
    DecisionLog,
    DecisionReview,
    FactArticle,
    IngestCursor,
    InterventionLog,
    LabelEvent,
    LLMUsage,
    Post,
    SystemLog,
)
from app.schemas.admin import (
    AdminOverviewOut,
    PaginatedSystemLogs,
    PaginatedTableData,
    SQLQueryRequest,
    SQLQueryResult,
    SystemLogOut,
    TableSummary,
)

router = APIRouter(prefix="/admin", tags=["admin"])

# Whitelist estrita de tabelas mapeadas para leitura administrativa
ALLOWED_TABLES: dict[str, type] = {
    "posts": Post,
    "decision_log": DecisionLog,
    "decision_reviews": DecisionReview,
    "intervention_logs": InterventionLog,
    "label_events": LabelEvent,
    "llm_usage": LLMUsage,
    "account_assessments": AccountAssessment,
    "crc_calibration": CRCCalibrationRecord,
    "system_logs": SystemLog,
    "fact_articles": FactArticle,
    "ingest_cursor": IngestCursor,
}

api_key_header = APIKeyHeader(name="X-Admin-Api-Key", auto_error=False)
bearer_security = HTTPBearer(auto_error=False)


def get_db():
    settings = get_settings()
    engine = create_engine(settings.database_url)
    with Session(engine) as session:
        yield session


def require_admin_key(
    header_key: str | None = Security(api_key_header),  # noqa: B008
    bearer_creds: HTTPAuthorizationCredentials | None = Security(bearer_security),  # noqa: B008
    settings: Settings = Depends(get_settings),  # noqa: B008
) -> str:
    """Valida se a chave de API administrativa fornecida corresponde a ADMIN_API_KEY."""
    expected = settings.admin_api_key.strip() if settings.admin_api_key else ""
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Acesso administrativo desativado: ADMIN_API_KEY não configurada no servidor.",
        )

    provided = header_key or (bearer_creds.credentials if bearer_creds else None)
    if not provided:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "Autenticação necessária. "
                "Forneça o header X-Admin-Api-Key ou Authorization: Bearer <chave>."
            ),
        )

    if not secrets.compare_digest(provided.strip(), expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Chave de API administrativa inválida.",
        )

    return provided


def check_ozone_health(url: str, timeout: float = 3.0) -> dict[str, Any]:
    """Confere o health público do Ozone (o caminho que passa pelo túnel)."""
    if not url:
        return {"configured": False, "reachable": None}
    try:
        response = httpx.get(url, timeout=timeout, headers={"User-Agent": "contraria-admin/1.0"})
    except httpx.HTTPError as exc:
        return {"configured": True, "reachable": False, "error": type(exc).__name__}
    return {
        "configured": True,
        "reachable": response.status_code == 200,
        "status_code": response.status_code,
    }


@router.get(
    "/overview",
    response_model=AdminOverviewOut,
    dependencies=[Depends(require_admin_key)],  # noqa: B008
)
def get_overview(
    db: Session = Depends(get_db),  # noqa: B008
    settings: Settings = Depends(get_settings),  # noqa: B008
):
    """Retorna uma visão geral completa das métricas, estatísticas e recursos do sistema."""
    now = datetime.now(UTC)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Métricas de posts
    posts_total = db.query(func.count(Post.uri)).scalar() or 0
    posts_by_status = {
        str(status_val or "sem_status"): count
        for status_val, count in db.query(Post.triage_status, func.count(Post.uri))
        .group_by(Post.triage_status)
        .all()
    }

    # Métricas de decisões
    decisions_total = db.query(func.count(DecisionLog.id)).scalar() or 0
    decisions_by_verdict = dict(
        db.query(DecisionLog.verdict, func.count(DecisionLog.id))
        .group_by(DecisionLog.verdict)
        .all()
    )

    # Intervenções
    interventions_total = db.query(func.count(InterventionLog.id)).scalar() or 0
    interventions_today = (
        db.query(func.count(InterventionLog.id))
        .filter(InterventionLog.created_at >= today_start)
        .scalar()
        or 0
    )

    # Uso de LLM
    today_date = now.date()
    tokens_in = db.query(func.sum(LLMUsage.tokens_in)).scalar() or 0
    tokens_out = db.query(func.sum(LLMUsage.tokens_out)).scalar() or 0
    llm_total_tokens = tokens_in + tokens_out
    llm_cost_total = db.query(func.sum(LLMUsage.cost_usd)).scalar() or 0.0
    llm_cost_today = (
        db.query(func.sum(LLMUsage.cost_usd)).filter(LLMUsage.date == today_date).scalar() or 0.0
    )

    # Bots
    bots_total = db.query(func.count(AccountAssessment.did)).scalar() or 0
    bots_labeled = (
        db.query(func.count(AccountAssessment.did))
        .filter(AccountAssessment.bot_label_applied.is_(True))
        .scalar()
        or 0
    )

    # Logs
    last_24h = now - timedelta(hours=24)
    logs_total = db.query(func.count(SystemLog.id)).scalar() or 0
    logs_errors_24h = (
        db.query(func.count(SystemLog.id))
        .filter(SystemLog.created_at >= last_24h, SystemLog.level == "ERROR")
        .scalar()
        or 0
    )

    # Rótulos do Ozone (outbox)
    labels_by_status = dict(
        db.query(LabelEvent.status, func.count(LabelEvent.id)).group_by(LabelEvent.status).all()
    )
    last_label_error = (
        db.query(LabelEvent.last_error, LabelEvent.subject_uri, LabelEvent.created_at)
        .filter(LabelEvent.last_error.isnot(None))
        .order_by(LabelEvent.id.desc())
        .first()
    )

    return AdminOverviewOut(
        timestamp=now,
        app_name=settings.app_name,
        posts={
            "total": posts_total,
            "by_status": posts_by_status,
        },
        decisions={
            "total": decisions_total,
            "by_verdict": decisions_by_verdict,
        },
        interventions={
            "total": interventions_total,
            "today": interventions_today,
            "daily_budget_max": settings.daily_max_interventions,
        },
        llm_usage={
            "total_tokens": int(llm_total_tokens),
            "cost_total_usd": round(float(llm_cost_total), 4),
            "cost_today_usd": round(float(llm_cost_today), 4),
            "daily_budget_usd": settings.daily_llm_budget_usd,
        },
        bots={
            "assessed_accounts": bots_total,
            "labeled_as_bot": bots_labeled,
            "threshold": settings.account_label_threshold,
        },
        logs={
            "total_records": logs_total,
            "errors_last_24h": logs_errors_24h,
        },
        labels={
            "by_status": labels_by_status,
            "pending": labels_by_status.get("pending", 0),
            "failed": labels_by_status.get("failed", 0),
            "last_error": (
                {
                    "error": last_label_error[0],
                    "subject": last_label_error[1],
                    "at": last_label_error[2],
                }
                if last_label_error
                else None
            ),
        },
        ozone=check_ozone_health(settings.ozone_health_url),
        config_summary={
            "verification_backend": settings.verification_backend,
            "intervention_dry_run": settings.intervention_dry_run,
            "pipeline_labeler_enabled": settings.pipeline_labeler_enabled,
            "worker_queue_max_pending": settings.worker_queue_max_pending,
            "worker_pipeline_concurrency": settings.worker_pipeline_concurrency,
        },
    )


@router.get(
    "/logs",
    response_model=PaginatedSystemLogs,
    dependencies=[Depends(require_admin_key)],  # noqa: B008
)
def list_logs(
    service: str | None = None,
    level: str | None = None,
    logger_name: str | None = Query(None, alias="logger"),
    search: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db),  # noqa: B008
):
    """Consulta paginada aos logs armazenados na tabela system_logs."""
    query = db.query(SystemLog)

    if service:
        query = query.filter(SystemLog.service == service)
    if level:
        query = query.filter(SystemLog.level == level.upper())
    if logger_name:
        query = query.filter(SystemLog.logger.ilike(f"%{logger_name}%"))
    if search:
        query = query.filter(SystemLog.message.ilike(f"%{search}%"))
    if since:
        query = query.filter(SystemLog.created_at >= since)
    if until:
        query = query.filter(SystemLog.created_at <= until)

    total = query.count()

    if order == "asc":
        items = (
            query.order_by(SystemLog.created_at.asc(), SystemLog.id.asc())
            .offset(offset)
            .limit(limit)
            .all()
        )
    else:
        items = (
            query.order_by(SystemLog.created_at.desc(), SystemLog.id.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

    return PaginatedSystemLogs(
        total=total,
        limit=limit,
        offset=offset,
        items=[SystemLogOut.model_validate(item) for item in items],
    )


@router.get(
    "/db/tables",
    response_model=list[TableSummary],
    dependencies=[Depends(require_admin_key)],  # noqa: B008
)
def list_tables(db: Session = Depends(get_db)):  # noqa: B008
    """Lista as tabelas disponíveis para consulta e a contagem de registros em cada uma."""
    summaries: list[TableSummary] = []
    for name, model_cls in ALLOWED_TABLES.items():
        count = db.query(func.count()).select_from(model_cls).scalar() or 0
        summaries.append(TableSummary(table_name=name, total_rows=count))
    return summaries


@router.get(
    "/db/tables/{table_name}",
    response_model=PaginatedTableData,
    dependencies=[Depends(require_admin_key)],  # noqa: B008
)
def get_table_data(
    table_name: str,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    order_by: str | None = None,
    order: str = Query("desc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db),  # noqa: B008
):
    """Consulta paginada de dados de uma tabela específica mapeada."""
    if table_name not in ALLOWED_TABLES:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Tabela '{table_name}' não existe ou não está liberada "
                "para leitura administrativa."
            ),
        )

    model_cls = ALLOWED_TABLES[table_name]
    query = db.query(model_cls)
    total_rows = db.query(func.count()).select_from(model_cls).scalar() or 0

    mapper = model_cls.__mapper__
    columns = [col.key for col in mapper.column_attrs]

    if order_by and order_by in columns:
        col_attr = getattr(model_cls, order_by)
        query = query.order_by(col_attr.asc() if order == "asc" else col_attr.desc())
    elif "created_at" in columns:
        query = query.order_by(model_cls.created_at.desc())
    elif "id" in columns:
        query = query.order_by(model_cls.id.desc())

    items = query.offset(offset).limit(limit).all()

    rows: list[dict[str, Any]] = []
    for item in items:
        row_dict: dict[str, Any] = {}
        for col_name in columns:
            val = getattr(item, col_name)
            if isinstance(val, datetime):
                row_dict[col_name] = val.isoformat()
            else:
                row_dict[col_name] = val
        rows.append(row_dict)

    return PaginatedTableData(
        table_name=table_name,
        total_rows=total_rows,
        limit=limit,
        offset=offset,
        columns=columns,
        rows=rows,
    )


@router.post(
    "/db/query",
    response_model=SQLQueryResult,
    dependencies=[Depends(require_admin_key)],  # noqa: B008
)
def execute_sql_query(
    body: SQLQueryRequest,
    db: Session = Depends(get_db),  # noqa: B008
):
    """Executa uma consulta SQL livre estritamente somente-leitura (SELECT)."""
    clean_sql = body.query.strip()

    # Impede múltiplas declarações separadas por ponto-e-vírgula
    if ";" in clean_sql.rstrip(";"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não é permitido concatenar múltiplas instruções SQL com ponto-e-vírgula.",
        )
    clean_sql = clean_sql.rstrip(";")

    # Remove comentários para análise léxica
    without_comments = re.sub(
        r"--.*?$|/\*.*?\*/", "", clean_sql, flags=re.MULTILINE | re.DOTALL
    ).strip()

    # Valida que começa com SELECT ou WITH (Common Table Expression)
    if not re.match(r"^(SELECT|WITH)\b", without_comments, re.IGNORECASE):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Apenas instruções SELECT ou WITH (somente-leitura) são permitidas.",
        )

    # Rejeita palavras-chave destrutivas ou de escrita
    forbidden_pattern = re.compile(
        r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE|REPLACE|GRANT|REVOKE|EXECUTE|CALL|COPY|VACUUM|REINDEX|LOCK)\b",
        re.IGNORECASE,
    )
    forbidden_match = forbidden_pattern.search(without_comments)
    if forbidden_match:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Comando proibido detectado: '{forbidden_match.group(1)}'. "
                "Apenas consultas somente-leitura são aceitas."
            ),
        )

    try:
        connection = db.connection()
        # Se for PostgreSQL, aplica transação READ ONLY e statement_timeout
        if db.bind and db.bind.dialect.name == "postgresql":
            connection.execute(text("SET statement_timeout = 5000"))
            connection.execute(text("SET TRANSACTION READ ONLY"))

        result = connection.execute(text(clean_sql))
        columns = list(result.keys()) if result.returns_rows else []

        rows: list[list[Any]] = []
        truncated = False
        if result.returns_rows:
            fetched = result.fetchmany(body.limit + 1)
            if len(fetched) > body.limit:
                truncated = True
                fetched = fetched[: body.limit]
            for row in fetched:
                row_items = []
                for val in row:
                    if isinstance(val, datetime):
                        row_items.append(val.isoformat())
                    else:
                        row_items.append(val)
                rows.append(row_items)

        return SQLQueryResult(
            columns=columns,
            rows=rows,
            row_count=len(rows),
            truncated=truncated,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erro na execução da consulta SQL: {exc}",
        ) from exc
