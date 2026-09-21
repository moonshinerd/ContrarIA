# CLAUDE.md

Guia para agentes (Claude Code) trabalhando neste repositório.

## Regras obrigatórias

- **Nunca** adicionar `Co-Authored-By` (de Claude ou de qualquer outro) em mensagens de commit.
- **Nunca** adicionar "Generated with Claude Code" ou qualquer atribuição a IA em commits, PRs, issues ou comentários.
- Nunca commitar direto na `main`: sempre `feature/<descrição-curta>` + PR com `Closes #N`.
- Nunca commitar segredos (`api/.env`, App Passwords do Bluesky, chaves de API).
- Textos para o time (issues, PRs, docs, commits) em **português**.

## O projeto

ContrarIA: agente contra desinformação política no **Bluesky**. O pipeline é coleta (Jetstream + searchPosts) → triagem → bot score → verificação (CoVe + Self-RAG + debate multiagente + CRC) → quote post e rótulo via labeler Ozone → log de decisões. Janela do MVP: 17/09 a 26/09/2026.

- Board: https://github.com/users/moonshinerd/projects/4. A lógica está em `docs/planejamento.md`.
- Requisitos RF/RNF e guiding questions: `docs/` (MkDocs).

## Estrutura

```
api/        FastAPI + worker (mesma imagem), Python 3.12, uv
  app/domain/     entidades puras = contrato entre duplas (mudou? avise no PR)
  app/models/     portas + implementações de LLM e classificadores
  app/clients/    adapters: Bluesky, Ozone, fontes de evidência (EvidenceSource)
  app/services/   casos de uso (coleta, triagem, verificação, intervenção)
  app/routers/v1/ HTTP fino, sem lógica de negócio
  app/prompts/    prompts versionados (<nome>_v<N>.txt)
  migrations/     Alembic (cada issue cria a sua migration)
research/   datasets, treino, benchmarks (fora da imagem da API)
deploy/     produção: Caddy + compose prod + Ozone
docs/       MkDocs (Material): planejamento, arquitetura, ADRs, atas
web/        painel React (pós-MVP)
```

Padrão herdado do Medscriba: `routers → services → domain`. Serviços dependem de portas abstratas (`LLMPort`, `EvidenceSource`, `TextClassifierPort`), e os testes usam fakes.

## Comandos

```bash
make setup        # api/.env + uv sync
make up / down    # docker compose: db (pgvector), api :8000, worker
make lint         # ruff check + format --check
make format
make test         # pytest
make migrate      # alembic upgrade head no container
make docs-serve   # MkDocs em :8001
```

O CI (`.github/workflows/ci.yml`) roda ruff, pytest e `mkdocs build --strict` em todo PR. Rode `make lint test` antes de abrir um PR.

Sem `uv` na máquina, rode tudo pelo Docker (a imagem é `--no-dev`, então o `uv sync` traz pytest e ruff, e `tests/` e `pyproject.toml` precisam ser montados):

```bash
docker compose run --rm --no-deps \
  -e BLUESKY_HANDLE= -e BLUESKY_APP_PASSWORD= \
  -v "$PWD/api/tests:/srv/tests" -v "$PWD/api/pyproject.toml:/srv/pyproject.toml" api \
  sh -c "uv sync --frozen -q && uv run --frozen pytest -q && uv run --frozen ruff check . && uv run --frozen ruff format --check ."
```

Os `-e BLUESKY_*=` vazios são necessários: o `env_file` injeta as credenciais reais do `api/.env` no container e o `test_login_without_credentials_fails_clearly` falha com elas. O CI não tem esse problema.

## Bluesky

- **Conta do bot:** `@contraria-bot.bsky.social` (handle público). O App Password fica só no `api/.env` (`BLUESKY_HANDLE`, `BLUESKY_APP_PASSWORD`), compartilhado com a dupla por canal privado e configurado no `.env` do servidor no deploy (#15). Nunca no repositório, em issue ou em PR.
- **Duas conexões** em `app/clients/bluesky_client.py`: AppView pública (`getPosts`, `getProfile`, `getAuthorFeed`, sem login) e PDS autenticado (`searchPosts` e escritas). A AppView pública devolve 403 no `searchPosts`.
- **Sessão persistida:** `createSession` tem limite de 300/dia e 30/5 min. A sessão fica em `BLUESKY_SESSION_PATH` (`/srv/data/bluesky.session`, volume `contraria-app-data`) e é reaproveitada. Retomar a sessão não valida nada na rede: um token expirado só aparece na chamada seguinte, e `_authenticated` refaz o login uma vez. Novas chamadas autenticadas devem passar por `_authenticated`, não por `_call`.
- **Limpar a sessão:** o SDK `atproto` guarda a sessão num dispatcher interno sem setter. `_discard_session` cria outro `AsyncClient` sobre o mesmo transporte HTTP.
- **Escritas no perfil:** só trate `RecordNotFound` como "perfil vazio" ao ler o record. Qualquer outro erro precisa subir, senão o `put_record` apaga nome, bio e avatar. Use `swapRecord`.
- **Scripts com a conta real** (via Docker, sem `uv`): `docker compose run --rm --no-deps api python -m app.scripts.bsky_smoke` só lê e faz login. `bsky_bot_setup` grava o self-label `bot` no perfil (idempotente): rode só de propósito.
- **Concorrência:** `api` e `worker` compartilham o arquivo de sessão, mas cada processo guarda a sua em memória. Prefira um só deles fazendo chamadas autenticadas.

## Issues e Project

- Toda tarefa é sub-issue de um épico e tem dupla (dois assignees), labels `area/*`, `prioridade/P0-P3`, `dupla/*`, milestone `MVP – Showcase (26/09)` e campos `Status`, `Área`, `Prioridade`, `Dupla`, `Início` e `Entrega` no Project.
- Dependências: só as reais, via *Blocked by* nativo (`POST /repos/{o}/{r}/issues/{n}/dependencies/blocked_by`).
- Duplas: Victor (`moonshinerd`) + Marlon (`MylinDev`); Raissa (`RaissaOliveira19`) + Samantha (`ySamantha`); Kyara (`Kyara2`) + Antonio (`AntonioLeonardoUNB`), estes últimos só na documentação.
- Views do Project com agrupamento: criar pela REST `POST /users/moonshinerd/projectsV2/4/views` (aceita `group_by`/`sort_by`). O GraphQL não aceita esses campos.
