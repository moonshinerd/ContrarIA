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

## Issues e Project

- Toda tarefa é sub-issue de um épico e tem dupla (dois assignees), labels `area/*`, `prioridade/P0-P3`, `dupla/*`, milestone `MVP – Showcase (26/09)` e campos `Status`, `Área`, `Prioridade`, `Dupla`, `Início` e `Entrega` no Project.
- Dependências: só as reais, via *Blocked by* nativo (`POST /repos/{o}/{r}/issues/{n}/dependencies/blocked_by`).
- Duplas: Victor (`moonshinerd`) + Marlon (`MylinDev`); Raissa (`RaissaOliveira19`) + Samantha (`ySamantha`); Kyara (`Kyara2`) + Antonio (`AntonioLeonardoUNB`), estes últimos só na documentação.
- Views do Project com agrupamento: criar pela REST `POST /users/moonshinerd/projectsV2/4/views` (aceita `group_by`/`sort_by`). O GraphQL não aceita esses campos.
