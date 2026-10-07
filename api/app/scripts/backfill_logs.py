"""Script CLI para importar histórico de logs (backfill) para a tabela system_logs.

Suporta leitura de arquivos ou stdin (ex.: pipes de `docker logs`).
Faz o parse inteligente de:
1. Linhas JSON geradas pelo JsonFormatter da aplicação;
2. Linhas encapsuladas pelo driver json-file do Docker;
3. Linhas em texto simples com timestamp/nível.

Uso:
    # A partir de arquivo:
    python -m app.scripts.backfill_logs --file /caminho/logs.json --service worker

    # A partir do pipe do Docker:
    docker logs --tail 5000 contraria-worker-1 | \
        python -m app.scripts.backfill_logs --service worker
"""

import argparse
import json
import re
import sys
from datetime import UTC, datetime
from typing import Any

from dateutil import parser as date_parser
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.orm.system_logs import SystemLog

TEXT_LOG_REGEX = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)\s*"
    r"(?:\[(?P<level>\w+)\])?\s*"
    r"(?:(?P<logger>[\w\.]+):)?\s*"
    r"(?P<msg>.*)$"
)


def parse_log_line(line: str, default_service: str = "worker") -> dict[str, Any] | None:
    line = line.strip()
    if not line:
        return None

    # Tenta parse como JSON
    payload = None
    try:
        data = json.loads(line)
        if isinstance(data, dict):
            # Se for encapsulado pelo Docker json-file
            if "log" in data and "stream" in data:
                raw_inner = data.get("log", "").strip()
                # Tenta parse do inner como JSON
                try:
                    payload = json.loads(raw_inner)
                except Exception:
                    # Se inner não for JSON, trata como texto e usa o time do docker
                    time_raw = data.get("time")
                    dt = date_parser.parse(time_raw) if time_raw else datetime.now(UTC)
                    return {
                        "created_at": dt,
                        "level": "INFO",
                        "logger": "docker.stdout",
                        "service": default_service,
                        "message": raw_inner,
                        "context": {"stream": data.get("stream")},
                    }
            else:
                payload = data
    except Exception:
        pass

    if payload and isinstance(payload, dict):
        # Campos típicos do JsonFormatter
        msg = payload.get("msg") or payload.get("message") or str(payload)
        level = payload.get("level", "INFO").upper()
        logger_name = payload.get("logger", "unknown")
        service = payload.get("service", default_service)

        ts_raw = payload.get("ts") or payload.get("timestamp") or payload.get("time")
        try:
            created_at = date_parser.parse(ts_raw) if ts_raw else datetime.now(UTC)
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=UTC)
        except Exception:
            created_at = datetime.now(UTC)

        reserved = {"ts", "timestamp", "time", "level", "logger", "msg", "message", "service"}
        context = {k: v for k, v in payload.items() if k not in reserved}
        return {
            "created_at": created_at,
            "level": level,
            "logger": logger_name,
            "service": service,
            "message": str(msg),
            "context": context if context else None,
        }

    # Fallback: linha de texto puro
    match = TEXT_LOG_REGEX.match(line)
    if match:
        ts_str = match.group("ts")
        level = (match.group("level") or "INFO").upper()
        logger_name = match.group("logger") or "text"
        msg = match.group("msg")
        try:
            created_at = date_parser.parse(ts_str)
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=UTC)
        except Exception:
            created_at = datetime.now(UTC)

        return {
            "created_at": created_at,
            "level": level,
            "logger": logger_name,
            "service": default_service,
            "message": msg,
            "context": None,
        }

    # Se não bater em regex, salva a linha inteira como mensagem
    return {
        "created_at": datetime.now(UTC),
        "level": "INFO",
        "logger": "raw",
        "service": default_service,
        "message": line,
        "context": None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Importa logs para a tabela system_logs.")
    parser.add_argument("--file", "-f", help="Caminho do arquivo de logs (se omitido, lê do stdin)")
    parser.add_argument(
        "--service",
        "-s",
        default="worker",
        help="Nome do serviço padrão (worker, api, etc.)",
    )
    parser.add_argument(
        "--batch-size", "-b", type=int, default=500, help="Tamanho do lote de inserção"
    )
    parser.add_argument("--dry-run", action="store_true", help="Faz o parse sem gravar no banco")
    args = parser.parse_args()

    settings = get_settings()
    engine = create_engine(settings.database_url)

    input_source = open(args.file, encoding="utf-8", errors="replace") if args.file else sys.stdin

    total_lines = 0
    parsed_count = 0
    inserted_count = 0
    batch: list[SystemLog] = []

    print(f"Iniciando importação de logs para service='{args.service}' (dry-run={args.dry_run})...")

    try:
        with Session(engine) as session:
            for line in input_source:
                total_lines += 1
                entry = parse_log_line(line, default_service=args.service)
                if not entry:
                    continue
                parsed_count += 1

                if not args.dry_run:
                    batch.append(SystemLog(**entry))
                    if len(batch) >= args.batch_size:
                        session.add_all(batch)
                        session.commit()
                        inserted_count += len(batch)
                        batch.clear()
                        print(
                            f"Progresso: {inserted_count} logs inseridos...",
                            end="\r",
                            flush=True,
                        )

            if batch and not args.dry_run:
                session.add_all(batch)
                session.commit()
                inserted_count += len(batch)
                batch.clear()

        print(
            f"\nConcluído! Total lido: {total_lines} linhas | "
            f"Identificados: {parsed_count} | Inseridos: {inserted_count}"
        )
    finally:
        if args.file and input_source is not sys.stdin:
            input_source.close()
        engine.dispose()


if __name__ == "__main__":
    main()
