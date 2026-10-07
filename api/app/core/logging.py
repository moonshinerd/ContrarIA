"""Logs estruturados: uma linha JSON por evento no stdout."""

import json
import logging
from datetime import UTC, datetime

from app.core.config import Settings


class JsonFormatter(logging.Formatter):
    _reserved = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        payload.update({k: v for k, v in record.__dict__.items() if k not in self._reserved})
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(settings: Settings) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(settings.log_level)


def enable_database_logging(settings: Settings, service_name: str | None = None) -> None:
    """Ativa o DatabaseLogHandler no root logger para persistir eventos em system_logs."""
    from app.core.db_logging import DatabaseLogHandler

    root = logging.getLogger()
    # Evita duplicar o handler
    for h in root.handlers:
        if isinstance(h, DatabaseLogHandler):
            return

    try:
        svc = service_name or getattr(settings, "service_name", "app")
        db_handler = DatabaseLogHandler(
            database_url=settings.database_url,
            service_name=svc,
        )
        root.addHandler(db_handler)
    except Exception:
        # Se falhar ao conectar ou instanciar, mantém apenas o log em stdout
        pass
