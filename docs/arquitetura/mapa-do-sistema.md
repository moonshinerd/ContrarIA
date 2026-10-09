# Mapa do sistema

Esta página é o **mapa de referência** do ContrarIA: mostra, em camadas (do contexto ao detalhe), de onde vêm os dados,
por onde passam e para onde vão. A estrutura segue o [modelo C4](https://c4model.com/) (contexto → contêineres →
componentes) com diagramas de sequência e de estados para o comportamento. Cada diagrama é seguido de uma tabela que
nomeia o código e a configuração de cada bloco.

!!! info "Como ler os diagramas"
    As cores têm o mesmo significado em todas as páginas desta seção e utilizam alto contraste visual.

    | Cor | Significado |
    |---|---|
    | :material-circle:{ style="color:#64748b" } cinza | Serviço externo (Bluesky, fontes de checagem, LLM, GitHub, Cloudflare) |
    | :material-circle:{ style="color:#0284c7" } azul-celeste | Entrada de dados (coleta, ingestão) |
    | :material-circle:{ style="color:#4f46e5" } índigo | Processamento do agente (triagem, verificação, decisão) |
    | :material-circle:{ style="color:#7e22ce" } roxo | Armazenamento (tabelas do Postgres) |
    | :material-circle:{ style="color:#d97706" } âmbar | Trava, filtro ou contrapressão |
    | :material-circle:{ style="color:#15803d" } verde | Saída pública (quote post, rótulo) |
    | :material-circle:{ style="color:#db2777" } rosa | Pessoa (usuário, operador, revisor) |

Para o fluxo lógico da análise veja [O Pipeline do Agente](pipeline.md); para o esquema do banco e a configuração,
[Dados, Infraestrutura e Deploy](dados-e-infra.md); para a operação diária, [Operação na VM](operacao-vm.md).

---

## 1. Contexto: o sistema e quem fala com ele

O ContrarIA tem **seis fluxos de entrada de dados** (detalhados na [seção 3](#3-pipelines-de-entrada); todos leem
conteúdo público, nenhum é caixa de mensagens privada) e **duas saídas públicas** (um quote post e um rótulo). O Bluesky é, ao mesmo tempo, a fonte e o destino.

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'fontSize': '14px', 'fontFamily': 'inherit', 'clusterBkg': 'transparent', 'clusterBorder': '#64748B', 'edgeLabelBackground': 'transparent' }}}%%
flowchart TD
    classDef ext fill:#F1F5F9,stroke:#64748B,stroke-width:2px,color:#0F172A
    classDef core fill:#EEF2FF,stroke:#4F46E5,stroke-width:2px,color:#1E1B4B
    classDef human fill:#FCE7F3,stroke:#DB2777,stroke-width:2px,color:#831843
    classDef out fill:#DCFCE7,stroke:#15803D,stroke-width:2px,color:#14532D

    subgraph IN["1. Entradas (Leitura Pública)"]
        direction LR
        JS["<span style='color:#0F172A'><b>Jetstream</b><br/>firehose posts pt</span>"]:::ext
        SRCH["<span style='color:#0F172A'><b>searchPosts</b><br/>posts mais populares</span>"]:::ext
        APPV["<span style='color:#0F172A'><b>AppView Bluesky</b><br/>perfil, feed e contexto</span>"]:::ext
        EVID["<span style='color:#0F172A'><b>Checagens & Notícias</b><br/>Google, Wiki, SearXNG, RSS</span>"]:::ext
        JS ~~~ SRCH ~~~ APPV ~~~ EVID
    end

    subgraph SYSTEM["2. Sistema ContrarIA"]
        direction TB
        CORE["<span style='color:#1E1B4B'><b>ContrarIA Core</b><br/>Worker, API, Jev e Banco</span>"]:::core
        OB["<span style='color:#1E1B4B'><b>Outbox de Rótulos</b><br/>persistência e repetições</span>"]:::core
        CORE -->|enfileira rótulo| OB
    end

    subgraph OUT["3. Saídas, LLM & Destinos"]
        direction LR
        LLM["<span style='color:#0F172A'><b>LiteLLM / OpenRouter</b><br/>redação e critic</span>"]:::ext
        QP["<span style='color:#14532D'><b>Quote Post Público</b><br/>@contraria-bot</span>"]:::out
        OZ["<span style='color:#14532D'><b>Labeler Ozone</b><br/>@contraria-labeler</span>"]:::out
        APP["<span style='color:#0F172A'><b>App Bluesky</b><br/>exibição de selos</span>"]:::ext
        QP --> APP
        OZ --> APP
    end

    AUTH(("<span style='color:#831843'><b>Autor</b><br/>do post</span>")):::human
    USER(("<span style='color:#831843'><b>Assinante</b><br/>do labeler</span>")):::human
    OPS(("<span style='color:#831843'><b>Operador</b><br/>Revisor</span>")):::human

    IN ==>|leitura pública| CORE
    CORE <-->|redação & critic| LLM
    CORE -->|publica citação| QP
    OB -->|emissão confiável| OZ

    APP -.->|notifica citação| AUTH
    USER -->|assina selos| APP
    OPS -->|auditoria e revisão| CORE

    CORE ~~~ LLM
```

| Ator ou sistema | Papel | Como o ContrarIA interage |
|---|---|---|
| Jetstream | Firehose público de commits do Bluesky | WebSocket de leitura; só a coleção `app.bsky.feed.post` |
| `searchPosts` | Busca do AppView | Uma consulta por palavra-chave, ordenada por `top` |
| AppView pública | Hidrata posts, perfis e fios | `getPosts`, `getProfile`, `getAuthorFeed`, `getPostThread` |
| PDS do bot | Onde o quote post é gravado | Escrita autenticada como `contraria-bot.bsky.social` |
| Labeler Ozone | Emite rótulos assinados | Conta separada, `contraria-labeler.bsky.social` |
| Fontes de evidência | Dão base à verificação | Consultadas por frase, nunca por post inteiro |
| LLM na nuvem | Só **redige** o texto do quote e audita sua coerência | Nunca decide o veredito (quem decide é o Jev local) |
| GitHub | Código, CI e deploy | OIDC, sem segredo guardado ([ADR 0020](../adr/0020-acesso-vm-tunel-cloudflare.md)) |

---

## 2. Contêineres: o que roda e como a rede chega

Tudo roda em **uma VM** com Docker Compose. A VM não aceita conexões de entrada: o tráfego público chega por um túnel
da Cloudflare publicado por SSH reverso ([ADR 0020](../adr/0020-acesso-vm-tunel-cloudflare.md)).

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'fontSize': '14px', 'fontFamily': 'inherit', 'clusterBkg': 'transparent', 'clusterBorder': '#64748B', 'edgeLabelBackground': 'transparent' }}}%%
flowchart TB
    classDef ext fill:#F1F5F9,stroke:#64748B,stroke-width:2px,color:#0F172A
    classDef ingest fill:#E0F2FE,stroke:#0284C7,stroke-width:2px,color:#0369A1
    classDef core fill:#EEF2FF,stroke:#4F46E5,stroke-width:2px,color:#1E1B4B
    classDef store fill:#F3E8FF,stroke:#7E22CE,stroke-width:2px,color:#581C87
    classDef guard fill:#FEF3C7,stroke:#D97706,stroke-width:2px,color:#78350F
    classDef out fill:#DCFCE7,stroke:#15803D,stroke-width:2px,color:#14532D

    NET(("<span style='color:#0F172A'><b>Internet</b></span>")):::ext
    GHA["<span style='color:#0F172A'><b>GitHub Actions</b><br/>token OIDC</span>"]:::ext
    CF["<span style='color:#0F172A'><b>Cloudflare</b><br/>contraria.schmidt.monster<br/>deploy-contraria.schmidt.monster</span>"]:::ext
    NET --> CF
    GHA --> CF
    CF --> TUN["<span style='color:#78350F'><b>Túnel contraria-vm</b><br/>no notebook talos</span>"]:::guard

    subgraph VM["VM de produção (Debian, 4 vCPU, sem porta de entrada)"]
        FWD["<span style='color:#78350F'><b>ozone-forward</b><br/>SSH reverso, saída pela 443</span>"]:::guard

        subgraph EDGE["Borda"]
            GW["<span style='color:#78350F'><b>gateway Nginx :3000</b></span>"]:::guard
            DH["<span style='color:#78350F'><b>deployhook :8081</b><br/>valida o JWT do GitHub</span>"]:::guard
        end

        subgraph APP["Aplicação (mesma imagem Docker)"]
            API["<span style='color:#1E1B4B'><b>api FastAPI :8000</b><br/>decisions, analyze, admin</span>"]:::core
            WK["<span style='color:#1E1B4B'><b>worker</b><br/>coleta, triagem, análise, rodadas</span>"]:::core
            JEV["<span style='color:#1E1B4B'><b>jev :8100</b><br/>NLI mDeBERTa, uma cópia</span>"]:::core
            SX["<span style='color:#0369A1'><b>searxng :8080</b><br/>metabuscador</span>"]:::ingest
        end

        subgraph LAB["Labeler"]
            OZ["<span style='color:#14532D'><b>ozone :3000</b></span>"]:::out
            OZD["<span style='color:#14532D'><b>ozone-daemon</b></span>"]:::out
            OZDB[("<span style='color:#581C87'><b>ozone-db</b><br/>Postgres 14</span>")]:::store
        end

        DB[("<span style='color:#581C87'><b>db</b><br/>Postgres 16 + pgvector</span>")]:::store
        HOST["<span style='color:#78350F'><b>systemd no host</b><br/>deploy-hook.path e deploy.sh</span>"]:::guard
    end

    TUN -.->|"ssh -R 3000 e 8081"| FWD
    FWD --> GW
    FWD --> DH
    GW -->|"/admin /v1 /health /docs"| API
    GW -->|"/xrpc e todo o resto"| OZ
    DH -->|"grava gatilho"| HOST
    HOST -->|"git reset, compose up, alembic"| APP

    API --> DB
    WK --> DB
    API --> JEV
    WK --> JEV
    WK --> SX
    OZ --> OZDB
    OZD --> OZDB
```

| Contêiner | Responsabilidade | Detalhe |
|---|---|---|
| `worker` | Único processo contínuo: coleta, atualização de engajamento, ingestão RSS, análise, rodadas de intervenção e repetição de rótulos | `python -m app.worker`, um *event loop* |
| `api` | HTTP fino: saúde, decisões, análise sob demanda, API administrativa somente-leitura | Atrás do `gateway` |
| `jev` | Classificador NLI compartilhado | Serializa as inferências; é o gargalo de CPU |
| `searxng` | Busca web self-hosted | Fonte primária da busca web |
| `db` | Estado da aplicação | `posts`, `decisions`, `label_events`, `system_logs`... |
| `gateway` | Roteia `/admin`, `/v1`, `/health` para a API e o resto para o Ozone | Nginx |
| `ozone`, `ozone-daemon`, `ozone-db` | Labeler da conta `contraria-labeler` | Anunciado no DID como `#atproto_labeler` |
| `deployhook` | Recebe o pedido de deploy autenticado por OIDC | Não executa nada: só grava o gatilho |

!!! warning "Dependência do túnel"
    Com o `talos` desligado ou sem rede, o **Ozone e o deploy ficam inacessíveis**, embora a coleta e a análise
    continuem. Foi o que causou rótulos perdidos antes da [outbox](#7-pipeline-de-saida-quote-post-e-rotulos): hoje o
    pedido de rótulo é guardado e repetido, e o `/admin/overview` mostra se o túnel responde.

---

## 3. Pipelines de entrada

O sistema tem **seis fluxos de entrada**. Três trazem **posts** (o que será analisado); os outros três trazem
**contexto** (o que sustenta a análise). Só o primeiro grupo cria linhas em `posts`.

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'fontSize': '14px', 'fontFamily': 'inherit', 'clusterBkg': 'transparent', 'clusterBorder': '#64748B', 'edgeLabelBackground': 'transparent' }}}%%
flowchart LR
    classDef ext fill:#F1F5F9,stroke:#64748B,stroke-width:2px,color:#0F172A
    classDef ingest fill:#E0F2FE,stroke:#0284C7,stroke-width:2px,color:#0369A1
    classDef core fill:#EEF2FF,stroke:#4F46E5,stroke-width:2px,color:#1E1B4B
    classDef store fill:#F3E8FF,stroke:#7E22CE,stroke-width:2px,color:#581C87
    classDef guard fill:#FEF3C7,stroke:#D97706,stroke-width:2px,color:#78350F
    classDef human fill:#FCE7F3,stroke:#DB2777,stroke-width:2px,color:#831843

    subgraph POSTS["A. Entradas que trazem POSTS"]
        direction TB
        E1["<span style='color:#0F172A'><b>E1. Jetstream</b><br/>WebSocket, tempo real</span>"]:::ext
        F1{"<span style='color:#78350F'>create + pt<br/>+ palavra-chave política</span>"}:::guard
        E1 --> F1

        E2["<span style='color:#0F172A'><b>E2. searchPosts</b><br/>a cada 10 min, 1 consulta<br/>por palavra, top 24 h, 25 por palavra</span>"]:::ext
        F2{"<span style='color:#78350F'>descarta URIs<br/>já conhecidas</span>"}:::guard
        E2 --> F2

        E3["<span style='color:#831843'><b>E3. POST /v1/analyze</b><br/>análise sob demanda</span>"]:::human
    end

    GATE{{"<span style='color:#78350F'><b>IngestGate</b><br/>teto de 100 na fila<br/>Jetstream não usa as 70 vagas<br/>reservadas ao searchPosts</span>"}}:::guard
    F1 --> GATE
    F2 --> GATE

    POSTSTB[("<span style='color:#581C87'><b>posts</b><br/>triage_status, priority<br/>source = jetstream ou search</span>")]:::store
    GATE -->|"cabe"| POSTSTB
    GATE -.->|"cheia: descarta"| X1(("<span style='color:#78350F'><b>descartado</b></span>")):::guard
    CUR[("<span style='color:#581C87'><b>ingest_cursor</b><br/>time_us</span>")]:::store
    E1 -.->|"retomar após reinício"| CUR

    subgraph CTX["B. Entradas que trazem CONTEXTO"]
        direction TB
        E4["<span style='color:#0369A1'><b>E4. Engajamento e prioridade</b><br/>EngagementRefresher, 5 min<br/>getPosts em lote</span>"]:::ingest
        E5["<span style='color:#0369A1'><b>E5. Acervo RSS de checagem</b><br/>FeedIngestor, 1 h<br/>embeddings MiniLM 384 d</span>"]:::ingest
        E6["<span style='color:#0369A1'><b>E6. Contexto durante a análise</b><br/>perfil, feed do autor, fio,<br/>link citado, evidências</span>"]:::ingest
    end

    E4 -->|"snapshots, velocidade,<br/>matriz GQ04"| SNAP[("<span style='color:#581C87'><b>post_engagement_snapshots</b></span>")]:::store
    E4 -->|"atualiza priority<br/>e triage_status"| POSTSTB
    E5 --> FA[("<span style='color:#581C87'><b>fact_articles</b><br/>pgvector</span>")]:::store

    POSTSTB -->|"monitor ou queued<br/>entre 3 h e 48 h de idade<br/>por priority"| POOL{{"<span style='color:#1E1B4B'><b>AnalysisPool</b><br/>concorrência configurável</span>"}}:::core
    E3 --> POOL
    FA -.->|"busca vetorial"| E6
    E6 --> POOL
    POOL --> PIPE["<span style='color:#1E1B4B'><b>PipelineService.analyze</b></span>"]:::core
```

| # | Entrada | Código | Cadência | Filtro ou limite | Destino |
|---|---|---|---|---|---|
| E1 | Jetstream | `JetstreamConsumer` em `jobs/collector.py` | Contínua | Só `create` de `app.bsky.feed.post`, idioma `pt*`, texto com palavra-chave de `domain/topics/politica.yaml` | `posts` (`source=jetstream`) |
| E2 | `searchPosts` | `SearchPoller` | 600 s | Uma consulta por palavra-chave (a API não tem `OR`), `sort=top`, últimas 24 h, 25 por palavra; só URIs novas | `posts` (`source=search`), com `priority` pela popularidade |
| E3 | Análise sob demanda | `POST /v1/analyze` em `routers/v1/decisions.py` | Sob demanda | Não passa pela fila de análise, pelo aging nem pela fila de intervenção: se o veredito pedir, a intervenção sai na hora | `decisions` |
| E4 | Engajamento | `EngagementRefresher` em `jobs/refresh_engagement.py` | 300 s | Posts das últimas 48 h, até 1.000 por ciclo; poda a fila a `WORKER_QUEUE_MAX_PENDING` | `post_engagement_snapshots`, `posts.priority`, `posts.triage_status` |
| E5 | Feeds RSS | `FeedIngestor` em `jobs/ingest_fact_articles.py` | 3.600 s | Só agências em `RSS_ENABLED_SOURCES` | `fact_articles` (com embedding) |
| E6 | Contexto da análise | `BlueskyClient`, `ArticleClient`, `evidence/*` | A cada análise | Resiliência por provedor ([ADR 0021](../adr/0021-resiliencia-das-fontes-de-evidencia.md)) | Memória do worker e `decisions.sources` |

**Contrapressão.** A coleta nunca analisa: só grava. O `IngestGate` mantém a fila abaixo do teto
(`WORKER_QUEUE_MAX_PENDING`); cheia, os posts novos do Jetstream são descartados e o `searchPosts` ainda consegue
entrar, porque `WORKER_QUEUE_SEARCH_RESERVE` reserva vagas para ele ([ADR 0018](../adr/0018-concorrencia-e-contrapressao-do-worker.md)).

### 3.1 O que o ContrarIA faz com reposts

Os **reposts não são posts novos** e não entram na fila. Eles aparecem em três lugares, cada um com um papel diferente:

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'fontSize': '14px', 'fontFamily': 'inherit', 'clusterBkg': 'transparent', 'clusterBorder': '#64748B', 'edgeLabelBackground': 'transparent' }}}%%
flowchart TB
    classDef ext fill:#F1F5F9,stroke:#64748B,stroke-width:2px,color:#0F172A
    classDef ingest fill:#E0F2FE,stroke:#0284C7,stroke-width:2px,color:#0369A1
    classDef core fill:#EEF2FF,stroke:#4F46E5,stroke-width:2px,color:#1E1B4B
    classDef store fill:#F3E8FF,stroke:#7E22CE,stroke-width:2px,color:#581C87
    classDef guard fill:#FEF3C7,stroke:#D97706,stroke-width:2px,color:#78350F

    R["<span style='color:#0F172A'><b>Repost no Bluesky</b><br/>(registro app.bsky.feed.repost)</span>"]:::ext

    R --x|"Jetstream pede só app.bsky.feed.post<br/>o registro de repost não é coletado"| J["<span style='color:#78350F'><b>Coleta</b></span>"]:::guard

    R -->|"soma em repost_count do post original"| ENG["<span style='color:#0369A1'><b>Engajamento</b><br/>getPosts, a cada 5 min</span>"]:::ingest
    ENG -->|"peso 2 na relevância<br/>e interação nova na velocidade"| PRIO[("<span style='color:#581C87'><b>posts.priority</b></span>")]:::store

    R -->|"aparece no feed do autor<br/>com reason = ReasonRepost"| AF["<span style='color:#0369A1'><b>getAuthorFeed</b><br/>até 100 itens do autor</span>"]:::ingest
    AF -->|"is_repost = true"| BF["<span style='color:#1E1B4B'><b>Características de bot</b><br/>content_repost_ratio</span>"]:::core
    BF --> BS["<span style='color:#1E1B4B'><b>Bot score da conta</b><br/>cache de 24 h</span>"]:::core
    BS --> GQ["<span style='color:#1E1B4B'><b>Matriz GQ01 e rótulo provavel-bot</b></span>"]:::core
```

| Onde o repost aparece | Efeito |
|---|---|
| Contagem de reposts do post original | Aumenta a **relevância** (peso 2, o mesmo de resposta) e conta como interação nova na **velocidade de propagação**, o que sobe a prioridade na fila |
| Feed do autor (`getAuthorFeed`) | Cada item recebe `is_repost`. A fração de reposts do autor vira a característica `content_repost_ratio` do **bot score** |
| Jetstream | **Ignorado**: o consumidor pede só `wantedCollections=app.bsky.feed.post` |

!!! note "Por que não coletar reposts"
    Um repost não traz texto próprio. A afirmação a verificar está no post original, que entra por E1 ou E2. Coletar
    o registro de repost só duplicaria o trabalho sem acrescentar uma alegação nova.

---

## 4. Ciclo de vida de um post

Duas colunas guardam o estado: `posts.triage_status` (a fila) e `decisions.action` (o resultado da análise). O diagrama
mostra como um post passa de uma para a outra.

```mermaid
stateDiagram-v2
    direction LR

    [*] --> Pendente: coletado (E1 ou E2)

    state "Fila de análise" as Fila {
        Pendente: monitor ou queued
        Maturando: idade menor que 3 h
        Elegivel: entre 3 h e 48 h
        Pendente --> Maturando: aging delay
        Maturando --> Elegivel: completa 3 h
    }

    Elegivel --> Analisado: AnalysisPool pega por priority
    Pendente --> Expirado: mais de 48 h, ou fila acima do teto
    Pendente --> Descartado: matriz GQ04 sem relevância
    Analisado --> Ignorado: 3 falhas seguidas

    state "Resultado da análise (decisions.action)" as Dec {
        IGNORE: IGNORE (bot pequeno)
        MONITOR: MONITOR (abstenção ou barrado)
        QUEUED: INTERVENE_QUEUED
        INTERVENE: INTERVENE
        ERRO: ERROR_INTERVENTION
    }

    Analisado --> IGNORE
    Analisado --> MONITOR
    Analisado --> QUEUED
    QUEUED --> INTERVENE: melhor da rodada de 15 min
    QUEUED --> MONITOR: preterido, travas, silêncio, critic ou reinício
    QUEUED --> ERRO: exceção na publicação

    INTERVENE --> [*]
    IGNORE --> [*]
    MONITOR --> [*]
    Expirado --> [*]
    Descartado --> [*]
    Ignorado --> [*]
    ERRO --> [*]
```

| Estado | Coluna | Quem define |
|---|---|---|
| `monitor`, `queued` | `triage_status` | Coleta e `EngagementRefresher` (matriz GQ04) |
| `processed`, `ignored`, `expired`, `discarded` | `triage_status` | Pool de análise, repositório e refresher. São **finais** |
| `IGNORE`, `MONITOR`, `INTERVENE_QUEUED` | `decisions.action` | `PipelineService` (matriz GQ01) |
| `INTERVENE`, `ERROR_INTERVENTION` | `decisions.action` | `InterventionQueue` ao fechar a rodada |

**Janela de maturação (aging).** Um post só pode ser analisado quando tem entre `POST_MIN_AGE_HOURS` (3 h) e
`POST_MAX_AGE_HOURS` (48 h). As primeiras horas dão tempo para a notícia ser publicada e indexada por buscadores e
agências de checagem; o limite superior evita analisar o que já esfriou. Posts acima de 48 h viram `expired` no
início do worker e a cada rodada de 15 min ([ADR 0022](../adr/0022-janela-de-maturacao-e-critic-semantico.md)).

---

## 5. Análise: o que acontece dentro do `PipelineService`

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'fontSize': '14px', 'fontFamily': 'inherit', 'clusterBkg': 'transparent', 'clusterBorder': '#64748B', 'edgeLabelBackground': 'transparent' }}}%%
flowchart TD
    classDef ext fill:#F1F5F9,stroke:#64748B,stroke-width:2px,color:#0F172A
    classDef core fill:#EEF2FF,stroke:#4F46E5,stroke-width:2px,color:#1E1B4B
    classDef store fill:#F3E8FF,stroke:#7E22CE,stroke-width:2px,color:#581C87
    classDef guard fill:#FEF3C7,stroke:#D97706,stroke-width:2px,color:#78350F
    classDef out fill:#DCFCE7,stroke:#15803D,stroke-width:2px,color:#14532D

    P["<span style='color:#1E1B4B'><b>Post elegível</b><br/>3 h a 48 h</span>"]:::core --> BOT["<span style='color:#1E1B4B'><b>Bot score da conta</b><br/>pesos em bot_weights.yaml<br/>cache de 24 h</span>"]:::core
    BOT --> ACC["<span style='color:#14532D'><b>AccountLabelService</b><br/>sincroniza provavel-bot</span>"]:::out
    P --> SPLIT["<span style='color:#78350F'><b>Frases candidatas</b><br/>até 6, com ancoramento factual</span>"]:::guard
    SPLIT -- "nenhuma" --> NOACT["<span style='color:#78350F'><b>Sem ação</b></span>"]:::guard
    SPLIT --> CITED["<span style='color:#1E1B4B'><b>Fonte citada pelo post</b><br/>NLI por trechos</span>"]:::core
    CITED -- "sustenta e fonte reconhecida" --> SC["<span style='color:#78350F'><b>source_consistent</b><br/>sem ação</span>"]:::guard
    CITED -- "senão" --> EVID["<span style='color:#1E1B4B'><b>Evidências por frase</b></span>"]:::core

    subgraph FONTES["Fontes de evidência (disjuntor por provedor)"]
        direction LR
        FC["<span style='color:#0F172A'><b>Google Fact Check</b></span>"]:::ext
        WP["<span style='color:#0F172A'><b>Wikipédia</b></span>"]:::ext
        WS["<span style='color:#0F172A'><b>SearXNG, DuckDuckGo</b></span>"]:::ext
        RS[("<span style='color:#581C87'><b>fact_articles</b><br/>busca vetorial</span>")]:::store
    end
    EVID --> FONTES
    FONTES --> REL["<span style='color:#78350F'><b>Filtro de relevância NLI</b><br/>gazetteer do IBGE<br/>descarta outra cidade ou zona</span>"]:::guard
    REL --> VER["<span style='color:#1E1B4B'><b>Veredito no Jev</b><br/>true, false, misleading<br/>neutro vira evidência insuficiente</span>"]:::core
    VER --> CRC["<span style='color:#78350F'><b>Gate CRC</b><br/>limiar calibrado</span>"]:::guard
    CRC -- "abaixo do limiar" --> IE["<span style='color:#78350F'><b>insufficient_evidence</b></span>"]:::guard
    CRC --> GQ{"<span style='color:#1E1B4B'><b>Matriz GQ01</b></span>"}:::core
    BOT --> GQ
    GQ -- "IGNORE ou MONITOR" --> LOG[("<span style='color:#581C87'><b>decisions</b></span>")]:::store
    GQ -- "INTERVENE_QUEUED" --> Q["<span style='color:#1E1B4B'><b>InterventionQueue</b></span>"]:::core
    Q --> LOG
```

Esta é a visão de blocos; as regras de cada etapa estão em [O Pipeline do Agente](pipeline.md). O que importa para o
mapa: **tudo termina em `decisions`**, e só `INTERVENE_QUEUED` segue para a saída.

---

## 6. Rodada de intervenção

A fila vive em memória e publica **no máximo um candidato por rodada** (`INTERVENTION_ROUND_MINUTES`, 15 min), nunca
entre 0 h e 7 h (Brasília).

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'fontSize': '14px', 'fontFamily': 'inherit', 'clusterBkg': 'transparent', 'clusterBorder': '#64748B', 'edgeLabelBackground': 'transparent' }}}%%
flowchart TD
    classDef ext fill:#F1F5F9,stroke:#64748B,stroke-width:2px,color:#0F172A
    classDef core fill:#EEF2FF,stroke:#4F46E5,stroke-width:2px,color:#1E1B4B
    classDef store fill:#F3E8FF,stroke:#7E22CE,stroke-width:2px,color:#581C87
    classDef guard fill:#FEF3C7,stroke:#D97706,stroke-width:2px,color:#78350F
    classDef out fill:#DCFCE7,stroke:#15803D,stroke-width:2px,color:#14532D

    R(["<span style='color:#1E1B4B'><b>Rodada vence</b><br/>a cada 15 min</span>"]):::core --> QH{"<span style='color:#78350F'>Horário de silêncio<br/>0 h às 7 h?</span>"}:::guard
    QH -- "sim" --> M0["<span style='color:#581C87'><b>Todos viram MONITOR</b></span>"]:::store
    QH -- "não" --> SORT["<span style='color:#1E1B4B'><b>Ordena por confiança</b><br/>do veredito</span>"]:::core
    SORT --> NEXT{"<span style='color:#1E1B4B'>Próximo candidato</span>"}:::core
    NEXT --> T1{"<span style='color:#78350F'>Travas do InterventionService<br/>confiança 0,8 ou mais<br/>não é o próprio bot nem bot<br/>1 quote por post e por autor em 24 h<br/>teto diário e pontos de escrita<br/>postgate permite citação</span>"}:::guard
    T1 -- "barrado" --> NEXT
    T1 -- "passou" --> SRC["<span style='color:#1E1B4B'><b>Revisão das fontes</b><br/>5 mais relevantes<br/>e leitura da matéria</span>"]:::core
    SRC --> LLM["<span style='color:#0F172A'><b>LLM redige o quote</b><br/>pergunta socrática</span>"]:::ext
    LLM --> CRIT{"<span style='color:#78350F'>Critic semântico<br/>a pergunta faz sentido com<br/>o POST, não só com a reportagem?</span>"}:::guard
    CRIT -- "veta" --> NEXT
    CRIT -- "aprova" --> DRY{"<span style='color:#78350F'>INTERVENTION_DRY_RUN?</span>"}:::guard
    DRY -- "sim" --> SIM["<span style='color:#78350F'><b>Simula, nada publicado</b></span>"]:::guard
    DRY -- "não" --> PUB["<span style='color:#14532D'><b>Publica o quote post</b><br/>até 300 graphemes, em fio se preciso</span>"]:::out
    PUB --> IL[("<span style='color:#581C87'><b>intervention_logs</b></span>")]:::store
    PUB --> LAB["<span style='color:#14532D'><b>Pede o rótulo</b><br/>possivel-desinformacao</span>"]:::out
    PUB --> REST["<span style='color:#581C87'><b>Demais candidatos viram MONITOR</b><br/>preterido por outro mais confiante</span>"]:::store
```

O **critic semântico** é o segundo passo de defesa contra alucinação: depois de redigido, o texto é auditado por um
prompt próprio (`semantic_critic_v1.txt`) que veta qualquer quote que atribua ao autor pessoas, declarações, leis ou
dados que **não estão no post**. A reportagem é só fonte de evidência: o destinatário da pergunta é sempre o post
([ADR 0022](../adr/0022-janela-de-maturacao-e-critic-semantico.md)).

---

## 7. Pipeline de saída: quote post e rótulos

Há duas saídas públicas, com **contas diferentes**: o quote sai de `contraria-bot`, o rótulo sai de
`contraria-labeler`. O rótulo passa pela **outbox** ([ADR 0023](../adr/0023-outbox-de-rotulos-do-ozone.md)), que o
registra e o repete se o Ozone estiver inacessível.

```mermaid
sequenceDiagram
    autonumber
    participant Q as InterventionQueue
    participant I as InterventionService
    participant PDS as PDS do bot
    participant OB as LabelOutbox
    participant DB as Postgres (label_events)
    participant OC as OzoneClient
    participant OZ as Ozone (via túnel)
    participant APP as App Bluesky

    Q->>I: execute_intervention(post, veredito)
    I->>PDS: createRecord (quote post)
    PDS-->>I: URI do quote
    I-->>Q: publicado
    Q->>OB: emit(post, possivel-desinformacao)
    OB->>DB: INSERT label_events (pending)
    OB->>OC: emit_label(create)
    OC->>OZ: tools.ozone.moderation.emitEvent (proxy do labeler)

    alt Ozone responde
        OZ-->>OC: 200
        OC-->>OB: ok
        OB->>DB: status = sent, sent_at
    else Ozone fora do ar (502, túnel caído)
        OZ--xOC: erro
        OC-->>OB: exceção
        OB->>DB: attempts + 1, last_error, next_attempt_at
        loop a cada 60 s no worker (espera dobra, até 1 h)
            OB->>OC: flush() reenvia os vencidos
            OC->>OZ: emitEvent
        end
        Note over OB,DB: após 8 falhas o evento vira failed
    end

    OZ-->>APP: rótulo assinado (queryLabels e subscribeLabels)
    APP-->>APP: exibe o aviso para quem assina o labeler
```

| Passo | Componente | Observação |
|---|---|---|
| Publicar | `InterventionService` + `BlueskyClient.quote_post` | `intervention_logs` alimenta as travas anti-loop e os limites diários |
| Registrar | `LabelOutbox.emit` ([label_outbox.py](https://github.com/moonshinerd/ContrarIA/blob/main/api/app/services/label_outbox.py)) | Pedido pendente igual é reaproveitado, sem duplicar |
| Emitir | `OzoneClient.emit_label` | Autentica como a conta do labeler, nunca como a do bot |
| Repetir | `run_due_label_flush` no laço do `worker` | `LABEL_RETRY_INTERVAL_SECONDS`, `LABEL_RETRY_MAX_ATTEMPTS` |
| Auditar | `/admin/overview` e `label_events` | Contagem por estado, último erro e health do Ozone |

---

## 8. Pipeline do Ozone: rótulos de post e de conta

Todos os rótulos saem pelo mesmo cliente, mas nascem de **três gatilhos** diferentes. A assinatura e a exibição ficam
com o app do Bluesky de cada pessoa (*opt-in*).

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'fontSize': '14px', 'fontFamily': 'inherit', 'clusterBkg': 'transparent', 'clusterBorder': '#64748B', 'edgeLabelBackground': 'transparent' }}}%%
flowchart LR
    classDef ext fill:#F1F5F9,stroke:#64748B,stroke-width:2px,color:#0F172A
    classDef core fill:#EEF2FF,stroke:#4F46E5,stroke-width:2px,color:#1E1B4B
    classDef store fill:#F3E8FF,stroke:#7E22CE,stroke-width:2px,color:#581C87
    classDef guard fill:#FEF3C7,stroke:#D97706,stroke-width:2px,color:#78350F
    classDef out fill:#DCFCE7,stroke:#15803D,stroke-width:2px,color:#14532D
    classDef human fill:#FCE7F3,stroke:#DB2777,stroke-width:2px,color:#831843

    subgraph GAT["Gatilhos (só com PIPELINE_LABELER_ENABLED)"]
        direction TB
        G1["<span style='color:#1E1B4B'><b>G1. Quote publicado</b><br/>post: possivel-desinformacao</span>"]:::core
        G2["<span style='color:#1E1B4B'><b>G2. Bot score alto</b><br/>conta: provavel-bot<br/>score 0,9 ou mais e 20 posts<br/>nega abaixo de 0,8 (histerese)</span>"]:::core
        G3["<span style='color:#831843'><b>G3. Revisão humana reverter</b><br/>nega possivel-desinformacao</span>"]:::human
    end

    OB["<span style='color:#78350F'><b>LabelOutbox</b><br/>registro e repetição</span>"]:::guard
    G1 --> OB
    G2 -->|"estado em account_assessments<br/>muda só após sucesso"| OZC
    G3 -->|"síncrono, erro vai ao revisor"| OZC
    OB --> OZC["<span style='color:#1E1B4B'><b>OzoneClient</b><br/>login como contraria-labeler</span>"]:::core
    OB --> LE[("<span style='color:#581C87'><b>label_events</b></span>")]:::store

    OZC -->|"emitEvent via proxy atproto_labeler"| PDSL["<span style='color:#0F172A'><b>PDS do labeler</b></span>"]:::ext
    PDSL -->|"encaminha ao serviço declarado no DID"| TUN["<span style='color:#78350F'><b>Cloudflare e túnel</b><br/>contraria.schmidt.monster</span>"]:::guard
    TUN --> GW["<span style='color:#78350F'><b>gateway Nginx</b></span>"]:::guard --> OZ["<span style='color:#14532D'><b>Ozone :3000</b></span>"]:::out
    OZ --> ODB[("<span style='color:#581C87'><b>ozone-db</b></span>")]:::store
    OZD["<span style='color:#14532D'><b>ozone-daemon</b></span>"]:::out --> ODB
    OZ --> SIGN["<span style='color:#14532D'><b>Assina o rótulo</b><br/>chave atproto_label</span>"]:::out

    SIGN --> APPV["<span style='color:#0F172A'><b>AppView e App Bluesky</b></span>"]:::ext
    USER(("<span style='color:#831843'><b>Quem assina o labeler</b></span>")):::human --> APPV
    APPV --> VIEW["<span style='color:#14532D'><b>Aviso informativo</b><br/>sem borrar o conteúdo</span>"]:::out

    REP(("<span style='color:#831843'><b>Denúncia de usuário</b></span>")):::human -.->|"fila nativa do Ozone<br/>o pipeline não consome"| OZ
```

| Rótulo | Alvo | Gatilho | Reversão |
|---|---|---|---|
| `possivel-desinformacao` | Post | Depois de um quote publicado e fora do *dry-run* | Revisão `reverter` nega o rótulo (`negate`), sem apagar o histórico |
| `provavel-bot` | Conta | A cada análise: score ≥ 0,9 e ≥ 20 posts | Nega quando o score cai abaixo de `limiar − histerese` |
| `evidencia-insuficiente` | Post | Declarado no labeler; usado só em testes de emissão | – |

Os três rótulos têm `severity: inform` e `blurs: none`: avisam, não escondem. O health do caminho público do Ozone
(`OZONE_HEALTH_URL`) aparece em `/admin/overview`, no campo `ozone`.

---

## 9. Entrega e operação

### 9.1 Deploy sem segredo guardado

```mermaid
sequenceDiagram
    autonumber
    actor DEV as Pessoa desenvolvedora
    participant GH as GitHub (PR e main)
    participant CI as CI (5 checks)
    participant DEP as deploy.yml
    participant CF as Cloudflare e túnel
    participant HOOK as deployhook
    participant HOST as systemd na VM
    participant APP as Compose (api, worker, jev)

    DEV->>GH: abre PR
    GH->>CI: ruff, pytest, docker build, mkdocs strict
    CI-->>GH: checks verdes
    DEV->>GH: merge na main
    GH->>DEP: push (ignora só docs)
    DEP->>GH: pede token OIDC (audience contraria-deploy)
    DEP->>CF: POST /deploy com o token
    CF->>HOOK: encaminha
    HOOK->>HOOK: valida JWT (RS256, repo, ref, workflow, environment)
    HOOK->>HOST: grava gatilho em /var/lib/contraria-deploy
    HOOK-->>DEP: 202 queued
    HOST->>APP: git reset origin/main, compose up --build, alembic upgrade head
    loop a cada 10 s
        DEP->>HOOK: GET /status
        HOOK-->>DEP: running ou ok ou failed
    end
    DEP-->>GH: conclusão do workflow
```

### 9.2 Observabilidade e API administrativa

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'fontSize': '14px', 'fontFamily': 'inherit', 'clusterBkg': 'transparent', 'clusterBorder': '#64748B', 'edgeLabelBackground': 'transparent' }}}%%
flowchart LR
    classDef ext fill:#F1F5F9,stroke:#64748B,stroke-width:2px,color:#0F172A
    classDef core fill:#EEF2FF,stroke:#4F46E5,stroke-width:2px,color:#1E1B4B
    classDef store fill:#F3E8FF,stroke:#7E22CE,stroke-width:2px,color:#581C87
    classDef guard fill:#FEF3C7,stroke:#D97706,stroke-width:2px,color:#78350F
    classDef human fill:#FCE7F3,stroke:#DB2777,stroke-width:2px,color:#831843
    classDef out fill:#DCFCE7,stroke:#15803D,stroke-width:2px,color:#14532D

    WK["<span style='color:#1E1B4B'><b>worker</b></span>"]:::core -->|"DatabaseLogHandler<br/>em lotes"| SL[("<span style='color:#581C87'><b>system_logs</b></span>")]:::store
    AP["<span style='color:#1E1B4B'><b>api</b></span>"]:::core -->|"DatabaseLogHandler"| SL
    DK["<span style='color:#78350F'><b>docker logs</b><br/>antigos</span>"]:::guard -->|"backfill_logs"| SL

    OPS(("<span style='color:#831843'><b>Operador</b></span>")):::human -->|"X-Admin-Api-Key"| ADM["<span style='color:#78350F'><b>API admin</b><br/>somente-leitura</span>"]:::guard
    ADM --> OV["<span style='color:#1E1B4B'><b>GET /admin/overview</b><br/>posts, decisões, intervenções,<br/>LLM, bots, labels, ozone</span>"]:::core
    ADM --> LG["<span style='color:#1E1B4B'><b>GET /admin/logs</b></span>"]:::core
    ADM --> TB["<span style='color:#1E1B4B'><b>GET /admin/db/tables</b></span>"]:::core
    ADM --> Q["<span style='color:#1E1B4B'><b>POST /admin/db/query</b><br/>SELECT e WITH</span>"]:::core
    OV --> LE[("<span style='color:#581C87'><b>label_events</b></span>")]:::store
    OV --> OZH["<span style='color:#14532D'><b>Health público do Ozone</b><br/>OZONE_HEALTH_URL</span>"]:::out
    LG --> SL
    TB --> SL & LE
```

---

## 10. Inventário de tabelas por fluxo

| Tabela | Quem escreve | Fluxo |
|---|---|---|
| `posts` | `JetstreamConsumer`, `SearchPoller`, `EngagementRefresher`, worker | Entradas E1, E2, E4 |
| `ingest_cursor` | `JetstreamConsumer` | E1 (retomada) |
| `post_engagement_snapshots` | `EngagementRefresher` | E4 |
| `fact_articles` | `FeedIngestor` | E5 |
| `account_assessments` | `BotScoringService`, `AccountLabelService` | Análise e rótulo de conta |
| `decisions`, `decision_reviews` | `PipelineService`, `InterventionQueue`, `POST /v1/decisions/{id}/review` | Análise e revisão |
| `intervention_logs` | `InterventionService` | Saída (quote) e travas |
| `label_events` | `LabelOutbox` | Saída (rótulo de post) |
| `crc_calibration`, `llm_usage` | Semente do worker, `LiteLLMModel` | Controle de risco e orçamento |
| `system_logs` | `DatabaseLogHandler`, `backfill_logs` | Observabilidade |

---

## 11. Limites que moldam o desenho

| Limite | Valor | Efeito |
|---|---|---|
| Fila de análise | `WORKER_QUEUE_MAX_PENDING=100` | Coleta descarta posts novos quando cheia |
| Reserva do `searchPosts` | `WORKER_QUEUE_SEARCH_RESERVE` (70 em produção) | O firehose não ocupa as vagas dos posts mais populares |
| Aging | 3 h a 48 h | Maturação da notícia e descarte do que esfriou |
| Concorrência de análises | `WORKER_PIPELINE_CONCURRENCY` (1 na VM) | O `jev` serializa a inferência |
| Rodada de intervenção | 1 quote por 15 min, silêncio 0 h–7 h | Respeita a diretriz de bots do Bluesky contra volume de interações não solicitadas |
| Teto diário | `DAILY_MAX_INTERVENTIONS`, pontos de escrita | Limita o impacto público |
| Orçamento de LLM | `DAILY_LLM_BUDGET_USD` | O LLM só redige e audita o quote |
| Repetição de rótulos | 60 s dobrando até 1 h, 8 tentativas | Tolera quedas do túnel sem perder o rótulo |

**Referências:** [Visão Geral](index.md), [O Pipeline do Agente](pipeline.md),
[Dados, Infraestrutura e Deploy](dados-e-infra.md), [Operação na VM](operacao-vm.md) e os [ADRs](../adr/index.md).
