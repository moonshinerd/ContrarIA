FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv

WORKDIR /srv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

# O serviço jev roda com mDeBERTa-v3 NLI, compartilhando as mesmas
# dependências base (PyTorch, Transformers) de api e worker, sem necessidade
# de compilação C++ de llama-cpp-python.
ARG INSTALL_JEV=false

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Pré-baixa o modelo NLI durante o build da imagem para que os pesos fiquem
# em cache (/root/.cache/huggingface), eliminando downloads em runtime.
RUN python -c "\
from transformers import AutoModelForSequenceClassification, AutoTokenizer; \
model_name = 'MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7'; \
AutoTokenizer.from_pretrained(model_name); \
AutoModelForSequenceClassification.from_pretrained(model_name); \
print('Modelo mDeBERTa pre-baixado com sucesso!')"

COPY app ./app
COPY alembic.ini ./
COPY migrations ./migrations

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
