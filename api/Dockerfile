FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv

WORKDIR /srv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

# Só o serviço `jev` (docker-compose.yml) passa INSTALL_JEV=true -- api e
# worker chamam esse serviço por HTTP, não precisam compilar llama-cpp-python
# (build-essential/cmake) nem baixar o modelo. Mantém o build de api/worker
# rápido, inclusive no CI, que só builda a imagem default (INSTALL_JEV=false).
ARG INSTALL_JEV=false

RUN if [ "$INSTALL_JEV" = "true" ]; then \
        apt-get update && apt-get install -y --no-install-recommends \
            build-essential cmake \
        && rm -rf /var/lib/apt/lists/*; \
    fi

COPY pyproject.toml uv.lock ./
RUN if [ "$INSTALL_JEV" = "true" ]; then \
        uv sync --frozen --no-dev --extra jev; \
    else \
        uv sync --frozen --no-dev; \
    fi

COPY app ./app
COPY alembic.ini ./
COPY migrations ./migrations

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
