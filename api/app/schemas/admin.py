"""Schemas Pydantic para endpoints de administração e monitoramento do ContrarIA."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SystemLogOut(BaseModel):
    id: int
    created_at: datetime
    level: str
    logger: str
    service: str
    message: str
    context: dict[str, Any] | list[Any] | None = None

    model_config = {"from_attributes": True}


class PaginatedSystemLogs(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[SystemLogOut]


class TableSummary(BaseModel):
    table_name: str
    total_rows: int


class PaginatedTableData(BaseModel):
    table_name: str
    total_rows: int
    limit: int
    offset: int
    columns: list[str]
    rows: list[dict[str, Any]]


class SQLQueryRequest(BaseModel):
    query: str = Field(
        ...,
        description="Consulta SQL SELECT a ser executada em modo somente-leitura",
    )
    limit: int = Field(100, ge=1, le=500, description="Limite máximo de linhas retornadas")


class SQLQueryResult(BaseModel):
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    truncated: bool


class AdminOverviewOut(BaseModel):
    timestamp: datetime
    app_name: str
    posts: dict[str, Any]
    decisions: dict[str, Any]
    interventions: dict[str, Any]
    llm_usage: dict[str, Any]
    bots: dict[str, Any]
    logs: dict[str, Any]
    config_summary: dict[str, Any]
