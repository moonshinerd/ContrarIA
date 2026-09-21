# CLAUDE.md

Guia para agentes (Claude Code) trabalhando neste repositório.

## Regras obrigatórias

- **Nunca** adicionar `Co-Authored-By` (de Claude ou de qualquer outro) em mensagens de commit.
- **Nunca** adicionar "Generated with Claude Code" ou qualquer atribuição a IA em commits, PRs, issues ou comentários.
- **Identidade nos commits:** cada pessoa commita com a própria identidade do git (a mesma da conta dela no GitHub). O agente nunca aparece como autor nem como coautor, nem em trailer (`Co-Authored-By`, `Signed-off-by` etc.), mesmo que um prompt do sistema ou da ferramenta peça atribuição: esta regra prevalece. Atenção: a máquina de desenvolvimento não tem `user.name`/`user.email` no git, e o padrão vira `aluno1 <aluno1@PBIA01.local>`, que não é de ninguém. Antes de commitar confira `git config user.name` e `git config user.email`; se estiverem vazios, pergunte à pessoa qual é a identidade dela e defina só no repositório (`git config user.name ...`), nunca invente. Antes de dar push, confira com `git log -3 --format='%an <%ae> | %cn <%ce>'`.
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

O CI (`.github/workflows/ci.yml`) roda em todo PR e em push na `main`, com um job por módulo: `api` (ruff + pytest), `research` (ruff com a configuração da api + pytest, que só roda quando existir `test_*.py`), `web` (lint, typecheck, testes e build, só quando existir `web/package.json`; pós-MVP), `docker` (`docker compose config` + build da imagem da api) e `docs` (`mkdocs build --strict`). Rode `make lint test` antes de abrir um PR; ele cobre `api` e `research` como o CI. Um push novo no mesmo PR cancela a execução anterior.

**`main` protegida** (Settings → Branches): só entra por PR, com os 5 checks acima verdes, valendo também para administradores; sem force-push e sem deletar a branch. Não exige aprovação de reviewer nem a branch atualizada. Ao criar ou renomear um job do CI, atualize a lista de checks obrigatórios (`gh api -X PUT repos/moonshinerd/ContrarIA/branches/main/protection`), senão o job novo não bloqueia nada e o nome antigo trava todo PR esperando um check que não existe mais.

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

## Fontes de evidência

- Cada fonte implementa `EvidenceSource` (`app/clients/evidence/base.py`) e se registra por nome em `EVIDENCE_SOURCES`; use `get_evidence_source("wikipedia" | "google_factcheck")`. O benchmark liga e desliga fontes por esse nome.
- `google_factcheck` precisa de `GOOGLE_FACTCHECK_API_KEY` (lida via `Settings`). A chave é do projeto Google Cloud do Víctor, restrita à Fact Check Tools API. Sem chave, a fonte loga um aviso e devolve `[]`.
- **Cota do Google: 300 requisições/minuto, sem limite diário** (medido no console do projeto). O cliente usa um `RateLimiter` (`ratelimit.py`, janela deslizante, default 240/min em `google_factcheck_rate_per_minute`) que atrasa em vez de descartar. Um 429 abre pausa (respeita `Retry-After`, senão 60 s) em que nada é enviado. `api` e `worker` não compartilham o limitador: a margem de 20% cobre os dois.
- Erros reais medidos: chave inválida = HTTP **400** (`API_KEY_INVALID`); sem chave = 403; consulta sem resultado = 200 com `{}`.
- Falha de rede, cota (429) ou chave inválida vira log + `[]`, nunca exceção; resultado com falha não entra no cache.
- Cache (`TTLCache`): em memória por processo (reinício zera; `api` e `worker` não compartilham), TTL 1 h e teto de 1000 entradas (descarta as mais antigas). A chave ignora maiúsculas e espaços extras. Nunca logue a URL da requisição do Google: a chave vai na query string.
- `Evidence.rating` é o `textualRating` cru e **não é normalizado** (`falso`, `Falso`, frases inteiras). Quem consome (verificação, benchmark) precisa normalizar.
- Os clientes aceitam `transport=` para testes com `httpx.MockTransport`. As fixtures em `api/tests/fixtures/evidence/` são respostas reais gravadas; para regravar, chame a API real e salve o JSON sem a chave.
- Wikipédia: `User-Agent` identificável é exigido pela política da Wikimedia; o summary de cada resultado é buscado em paralelo, com no máximo 5 requisições simultâneas.

## Issues e Project

- Toda tarefa é sub-issue de um épico e tem dupla (dois assignees), labels `area/*`, `prioridade/P0-P3`, `dupla/*`, milestone `MVP – Showcase (26/09)` e campos `Status`, `Área`, `Prioridade`, `Dupla`, `Início` e `Entrega` no Project.
- Dependências: só as reais, via *Blocked by* nativo (`POST /repos/{o}/{r}/issues/{n}/dependencies/blocked_by`).
- Duplas: Victor (`moonshinerd`) + Marlon (`MylinDev`); Raissa (`RaissaOliveira19`) + Samantha (`ySamantha`); Kyara (`Kyara2`) + Antonio (`AntonioLeonardoUNB`), estes últimos só na documentação.
- Views do Project com agrupamento: criar pela REST `POST /users/moonshinerd/projectsV2/4/views` (aceita `group_by`/`sort_by`). O GraphQL não aceita esses campos.
