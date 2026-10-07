"""Handler de logging para persistência assíncrona e resiliente no banco de dados."""

import atexit
import logging
import queue
import threading
import time
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.orm.system_logs import SystemLog

logger = logging.getLogger("contraria.db_logging")

IGNORE_LOGGER_PREFIXES = (
    "sqlalchemy",
    "alembic",
    "psycopg",
    "uvicorn.access",
    "contraria.db_logging",
)


class DatabaseLogHandler(logging.Handler):
    """Grava logs na tabela system_logs em lote usando uma thread de segundo plano."""

    def __init__(
        self,
        database_url: str,
        service_name: str = "app",
        batch_size: int = 50,
        flush_interval_seconds: float = 1.0,
        max_queue_size: int = 10000,
    ) -> None:
        super().__init__()
        self.service_name = service_name
        self.batch_size = batch_size
        self.flush_interval = flush_interval_seconds
        self.queue: queue.Queue[dict[str, Any] | None] = queue.Queue(maxsize=max_queue_size)
        self._stop_event = threading.Event()
        self._reserved = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}

        self.engine = create_engine(
            database_url,
            pool_pre_ping=True,
            pool_size=2,
            max_overflow=2,
        )

        self.worker_thread = threading.Thread(
            target=self._worker_loop,
            name=f"db-logger-{service_name}",
            daemon=True,
        )
        self.worker_thread.start()
        atexit.register(self.close)

    def emit(self, record: logging.LogRecord) -> None:
        # Previne recursão infinita e ruído de drivers internos
        if record.name.startswith(IGNORE_LOGGER_PREFIXES):
            return

        try:
            extra = {k: v for k, v in record.__dict__.items() if k not in self._reserved}
            if record.exc_info:
                extra["exc_info"] = self.format(record) if not record.exc_text else record.exc_text

            entry = {
                "created_at": datetime.fromtimestamp(record.created, UTC),
                "level": record.levelname,
                "logger": record.name,
                "service": getattr(record, "service", self.service_name),
                "message": record.getMessage(),
                "context": extra if extra else None,
            }
            self.queue.put_nowait(entry)
        except queue.Full:
            # Fila cheia: descarta para não travar a aplicação sob carga extrema
            pass
        except Exception:
            # Nunca propaga exceção de logging para o chamador
            self.handleError(record)

    def _worker_loop(self) -> None:
        batch: list[dict[str, Any]] = []
        last_flush = time.monotonic()

        while not self._stop_event.is_set():
            try:
                timeout = max(0.1, self.flush_interval - (time.monotonic() - last_flush))
                item = self.queue.get(timeout=timeout)
                if item is None:
                    # Sinal de parada
                    break
                batch.append(item)
            except queue.Empty:
                pass

            now = time.monotonic()
            if batch and (len(batch) >= self.batch_size or now - last_flush >= self.flush_interval):
                self._flush_batch(batch)
                batch.clear()
                last_flush = now

        # Esvazia o restante ao parar
        if batch:
            self._flush_batch(batch)
            batch.clear()

        while not self.queue.empty():
            try:
                item = self.queue.get_nowait()
                if item is not None:
                    batch.append(item)
            except queue.Empty:
                break
        if batch:
            self._flush_batch(batch)

    def _flush_batch(self, batch: list[dict[str, Any]]) -> None:
        if not batch:
            return
        try:
            with Session(self.engine) as session:
                objects = [
                    SystemLog(
                        created_at=item["created_at"],
                        level=item["level"],
                        logger=item["logger"],
                        service=item["service"],
                        message=item["message"],
                        context=item["context"],
                    )
                    for item in batch
                ]
                session.add_all(objects)
                session.commit()
        except Exception:
            # Se o banco falhar, não derruba nada; apenas descarta e tenta na próxima
            pass

    def close(self) -> None:
        if not self._stop_event.is_set():
            self._stop_event.set()
            try:
                self.queue.put_nowait(None)
            except Exception:
                pass
            if self.worker_thread.is_alive():
                self.worker_thread.join(timeout=2.0)
            try:
                self.engine.dispose()
            except Exception:
                pass
        super().close()
