# Arquitetura

## Pipeline

```mermaid
flowchart LR
    J[Jetstream<br/>tempo real] --> C[Coleta<br/>RF01]
    S[searchPosts<br/>posts top] --> C
    C --> T[Filtro temático<br/>RF09]
    T --> R[Relevância e velocidade<br/>RF08 / RF10]
    R --> B[Bot score<br/>RF02 / RF12]
    R --> F[Pré-filtro clássico<br/>fake news]
    B --> P{Priorização<br/>RF04}
    F --> P
    P -- baixo --> M[Monitorar]
    P -- alto --> V[Verificação<br/>CoVe + Self-RAG + MAD + CRC]
    V -- INSUFFICIENT_EVIDENCE --> M
    V -- falso/enganoso --> I[Quote post<br/>RF05 / RF06]
    V --> L[Labeler Ozone<br/>RF07]
    I --> D[(Log de decisões<br/>RF13 / RNF06)]
    L --> D
    M --> D
```

## Organização do código

```
ContrarIA/
├── api/                 # FastAPI + worker (mesma imagem)
│   └── app/
│       ├── main.py      # HTTP: /health, decisões, verificação sob demanda
│       ├── worker.py    # loop do pipeline
│       ├── core/        # config, logging
│       ├── routers/v1/  # camada HTTP fina
│       ├── schemas/     # contratos Pydantic
│       ├── domain/      # entidades e regras puras (contrato entre duplas)
│       ├── services/    # casos de uso: coleta, triagem, verificação, intervenção
│       ├── models/      # portas + implementações de LLM e classificadores
│       ├── clients/     # adapters de I/O: Bluesky, Ozone, fontes de evidência
│       ├── repositories/
│       ├── db/          # ORM (SQLAlchemy) + migrations (Alembic)
│       └── prompts/     # prompts versionados (promotor_v1.txt, ...)
├── research/            # datasets, treino do pré-filtro, benchmarks
├── deploy/              # Caddy + compose de produção + Ozone
├── web/                 # painel React (pós-MVP)
└── docs/                # este site (MkDocs)
```

Padrão herdado do [Medscriba](https://github.com/Medscriba/medscriba): `domain/` não conhece framework; `models/` e `clients/evidence/` expõem **portas abstratas**, então cada dupla desenvolve contra a interface com fakes nos testes, e as issues de integração só ligam as pontas.
