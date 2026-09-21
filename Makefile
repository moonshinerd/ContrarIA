.PHONY: help setup up down logs lint format test migrate docs-serve docs-build

help:
	@echo "make setup       - cria api/.env e instala dependências locais (uv)"
	@echo "make up          - sobe db, api e worker (docker compose)"
	@echo "make down        - derruba os containers"
	@echo "make logs        - acompanha logs de api e worker"
	@echo "make lint        - ruff check + format --check (api e research)"
	@echo "make format      - aplica ruff format + fix (api e research)"
	@echo "make test        - pytest da api e do research (igual ao CI)"
	@echo "make migrate     - alembic upgrade head dentro do container da api"
	@echo "make docs-serve  - MkDocs local em http://127.0.0.1:8001"

setup:
	@test -f api/.env || cp api/.env.example api/.env
	cd api && uv sync

up:
	@test -f api/.env || cp api/.env.example api/.env
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f api worker

# research/ não tem pyproject próprio: usa o ruff e a configuração da api
lint:
	cd api && uv run ruff check . && uv run ruff format --check .
	cd api && uv run ruff check --config pyproject.toml ../research && uv run ruff format --check --config pyproject.toml ../research

format:
	cd api && uv run ruff format . && uv run ruff check --fix .
	cd api && uv run ruff format --config pyproject.toml ../research && uv run ruff check --fix --config pyproject.toml ../research

test:
	cd api && uv run pytest
	@if find research -name 'test_*.py' -o -name '*_test.py' | grep -q .; then \
		cd research && uv run --no-project --with-requirements requirements.txt python -m pytest; \
	else echo "research/ ainda não tem testes; nada a rodar"; fi

migrate:
	docker compose exec api alembic upgrade head

docs-serve:
	uvx --with mkdocs-material mkdocs serve -a 127.0.0.1:8001

docs-build:
	uvx --with mkdocs-material mkdocs build --strict
