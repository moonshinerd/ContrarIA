# Mapa do sistema

Esta página é o **mapa de referência** do ContrarIA: mostra, em camadas (do contexto ao detalhe), de onde vêm os dados,
por onde passam e para onde vão. A estrutura segue o [modelo C4](https://c4model.com/) (contexto → contêineres →
componentes) com diagramas de sequência e de estados para o comportamento. Cada diagrama é seguido de uma tabela que
nomeia o código e a configuração de cada bloco.

!!! info "Como ler os diagramas"
    As cores têm o mesmo significado em todas as páginas desta seção.

    | Cor | Significado |
    |---|---|
    | :material-circle:{ style="color:#475569" } cinza | Serviço externo (Bluesky, fontes de checagem, LLM, GitHub, Cloudflare) |
    | :material-circle:{ style="color:#0e7490" } azul-petróleo | Entrada de dados (coleta, ingestão) |
    | :material-circle:{ style="color:#2563eb" } azul | Processamento do agente (triagem, verificação, decisão) |
    | :material-circle:{ style="color:#7c3aed" } roxo | Armazenamento (tabelas do Postgres) |
    | :material-circle:{ style="color:#d97706" } laranja | Trava, filtro ou contrapressão |
    | :material-circle:{ style="color:#16a34a" } verde | Saída pública (quote post, rótulo) |
    | :material-circle:{ style="color:#db2777" } rosa | Pessoa (usuário, operador, revisor) |

Para o fluxo lógico da análise veja [O Pipeline do Agente](pipeline.md); para o esquema do banco e a configuração,
[Dados, Infraestrutura e Deploy](dados-e-infra.md); para a operação diária, [Operação na VM](operacao-vm.md).

---

## 1. Contexto: o sistema e quem fala com ele

O ContrarIA tem **seis fluxos de entrada de dados** (detalhados na [seção 3](#3-pipelines-de-entrada); todos leem
conteúdo público, nenhum é caixa de mensagens privada) e **duas saídas públicas** (um quote post e um rótulo). O Bluesky é, ao mesmo tempo, a fonte e o destino.

```mermaid
flowchart LR
    classDef ext fill:#475569,stroke:#1e293b,color:#fff
    classDef core fill:#2563eb,stroke:#1e3a8a,color:#fff
    classDef human fill:#db2777,stroke:#831843,color:#fff
    classDef out fill:#16a34a,stroke:#14532d,color:#fff

    subgraph IN["1. Entradas (Leitura Pública)"]
        direction TB
        JS["Jetstream<br/>firehose de posts pt"]:::ext
        SRCH["searchPosts<br/>posts mais populares"]:::ext
        APPV["AppView Bluesky<br/>perfil, feed, contexto do fio"]:::ext
        EVID["Checagens & Notícias<br/>Google, Wiki, SearXNG, RSS"]:::ext
    end

    subgraph SYSTEM["2. Sistema ContrarIA"]
        direction TB
        CORE["ContrarIA Core<br/>Worker, API, Jev e Banco"]:::core
        OB["Outbox de Rótulos<br/>persistência e repetições"]:::core
        CORE --> OB
    end

    subgraph OUT["3. Saídas, LLM & Destinos"]
        direction TB
        LLM["LiteLLM / OpenRouter<br/>redação socrática e critic"]:::ext
        QP["Quote Post Público<br/>@contraria-bot.bsky.social"]:::out
        OZ["Labeler Ozone<br/>@contraria-labeler.bsky.social"]:::out
        APP["App Bluesky<br/>notificação e exibição de selos"]:::ext
        QP --> APP
        OZ --> APP
    end

    AUTH(("Autor do post<br/>citado")):::human
    USER(("Assinante<br/>do labeler")):::human
    OPS(("Operador /<br/>Revisor")):::human

    JS -->|"tempo real"| CORE
    SRCH -->|"top 24 h"| CORE
    APPV -->|"engajamento"| CORE
    EVID -->|"evidências"| CORE

    CORE <-->|"redação & critic"| LLM
    CORE -->|"publicação"| QP
    OB -->|"emissão confiável"| OZ

    APP -.->|"notifica citação"| AUTH
    USER -->|"assina selos"| APP
    OPS -->|"auditoria e revisão"| CORE
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
flowchart TB
    classDef ext fill:#475569,stroke:#1e293b,color:#fff
    classDef ingest fill:#0e7490,stroke:#164e63,color:#fff
    classDef core fill:#2563eb,stroke:#1e3a8a,color:#fff
    classDef store fill:#7c3aed,stroke:#4c1d95,color:#fff
    classDef guard fill:#d97706,stroke:#78350f,color:#fff
    classDef out fill:#16a34a,stroke:#14532d,color:#fff

    NET(("Internet")):::ext
    GHA["GitHub Actions<br/>token OIDC"]:::ext
    CF["Cloudflare<br/>contraria.schmidt.monster<br/>deploy-contraria.schmidt.monster"]:::ext
    NET --> CF
    GHA --> CF
    CF --> TUN["Túnel contraria-vm<br/>no notebook talos"]:::guard

    subgraph VM["VM de produção (Debian, 4 vCPU, sem porta de entrada)"]
        FWD["ozone-forward<br/>SSH reverso, saída pela 443"]:::guard

        subgraph EDGE["Borda"]
            GW["gateway Nginx :3000"]:::guard
            DH["deployhook :8081<br/>valida o JWT do GitHub"]:::guard
        end

        subgraph APP["Aplicação (mesma imagem Docker)"]
            API["api FastAPI :8000<br/>decisions, analyze, admin"]:::core
            WK["worker<br/>coleta, triagem, análise, rodadas"]:::core
            JEV["jev :8100<br/>NLI mDeBERTa, uma cópia"]:::core
            SX["searxng :8080<br/>metabuscador"]:::ingest
        end

        subgraph LAB["Labeler"]
            OZ["ozone :3000"]:::out
            OZD["ozone-daemon"]:::out
            OZDB[("ozone-db<br/>Postgres 14")]:::store
        end

        DB[("db<br/>Postgres 16 + pgvector")]:::store
        HOST["systemd no host<br/>deploy-hook.path e deploy.sh"]:::guard
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
flowchart LR
    classDef ext fill:#475569,stroke:#1e293b,color:#fff
    classDef ingest fill:#0e7490,stroke:#164e63,color:#fff
    classDef core fill:#2563eb,stroke:#1e3a8a,color:#fff
    classDef store fill:#7c3aed,stroke:#4c1d95,color:#fff
    classDef guard fill:#d97706,stroke:#78350f,color:#fff
    classDef human fill:#db2777,stroke:#831843,color:#fff

    subgraph POSTS["A. Entradas que trazem POSTS"]
        direction TB
        E1["E1. Jetstream<br/>WebSocket, tempo real"]:::ext
        F1{"create + pt<br/>+ palavra-chave política"}:::guard
        E1 --> F1

        E2["E2. searchPosts<br/>a cada 10 min, 1 consulta<br/>por palavra, top 24 h, 25 por palavra"]:::ext
        F2{"descarta URIs<br/>já conhecidas"}:::guard
        E2 --> F2

        E3["E3. POST /v1/analyze<br/>análise sob demanda"]:::human
    end

    GATE{{"IngestGate<br/>teto de 100 na fila<br/>Jetstream não usa as 70 vagas<br/>reservadas ao searchPosts"}}:::guard
    F1 --> GATE
    F2 --> GATE

    POSTSTB[("posts<br/>triage_status, priority<br/>source = jetstream ou search")]:::store
    GATE -->|"cabe"| POSTSTB
    GATE -.->|"cheia: descarta"| X1(("descartado")):::guard
    CUR[("ingest_cursor<br/>time_us")]:::store
    E1 -.->|"retomar após reinício"| CUR

    subgraph CTX["B. Entradas que trazem CONTEXTO"]
        direction TB
        E4["E4. Engajamento e prioridade<br/>EngagementRefresher, 5 min<br/>getPosts em lote"]:::ingest
        E5["E5. Acervo RSS de checagem<br/>FeedIngestor, 1 h<br/>embeddings MiniLM 384 d"]:::ingest
        E6["E6. Contexto durante a análise<br/>perfil, feed do autor, fio,<br/>link citado, evidências"]:::ingest
    end

    E4 -->|"snapshots, velocidade,<br/>matriz GQ04"| SNAP[("post_engagement_snapshots")]:::store
    E4 -->|"atualiza priority<br/>e triage_status"| POSTSTB
    E5 --> FA[("fact_articles<br/>pgvector")]:::store

    POSTSTB -->|"monitor ou queued<br/>entre 3 h e 48 h de idade<br/>por priority"| POOL{{"AnalysisPool<br/>concorrência configurável"}}:::core
    E3 --> POOL
    FA -.->|"busca vetorial"| E6
    E6 --> POOL
    POOL --> PIPE["PipelineService.analyze"]:::core
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
flowchart TB
    classDef ext fill:#475569,stroke:#1e293b,color:#fff
    classDef ingest fill:#0e7490,stroke:#164e63,color:#fff
    classDef core fill:#2563eb,stroke:#1e3a8a,color:#fff
    classDef store fill:#7c3aed,stroke:#4c1d95,color:#fff
    classDef guard fill:#d97706,stroke:#78350f,color:#fff

    R["Repost no Bluesky<br/>(registro app.bsky.feed.repost)"]:::ext

    R --x|"Jetstream pede só app.bsky.feed.post<br/>o registro de repost não é coletado"| J["Coleta"]:::guard

    R -->|"soma em repost_count do post original"| ENG["Engajamento<br/>getPosts, a cada 5 min"]:::ingest
    ENG -->|"peso 2 na relevância<br/>e interação nova na velocidade"| PRIO[("posts.priority")]:::store

    R -->|"aparece no feed do autor<br/>com reason = ReasonRepost"| AF["getAuthorFeed<br/>até 100 itens do autor"]:::ingest
    AF -->|"is_repost = true"| BF["Características de bot<br/>content_repost_ratio"]:::core
    BF --> BS["Bot score da conta<br/>cache de 24 h"]:::core
    BS --> GQ["Matriz GQ01 e rótulo provavel-bot"]:::core
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
flowchart TD
    classDef ext fill:#475569,stroke:#1e293b,color:#fff
    classDef core fill:#2563eb,stroke:#1e3a8a,color:#fff
    classDef store fill:#7c3aed,stroke:#4c1d95,color:#fff
    classDef guard fill:#d97706,stroke:#78350f,color:#fff
    classDef out fill:#16a34a,stroke:#14532d,color:#fff

    P["Post elegível<br/>3 h a 48 h"]:::core --> BOT["Bot score da conta<br/>pesos em bot_weights.yaml<br/>cache de 24 h"]:::core
    BOT --> ACC["AccountLabelService<br/>sincroniza provavel-bot"]:::out
    P --> SPLIT["Frases candidatas<br/>até 6, com ancoramento factual"]:::guard
    SPLIT -- "nenhuma" --> NOACT["Sem ação"]:::guard
    SPLIT --> CITED["Fonte citada pelo post<br/>NLI por trechos"]:::core
    CITED -- "sustenta e fonte reconhecida" --> SC["source_consistent<br/>sem ação"]:::guard
    CITED -- "senão" --> EVID["Evidências por frase"]:::core

    subgraph FONTES["Fontes de evidência (disjuntor por provedor)"]
        direction LR
        FC["Google Fact Check"]:::ext
        WP["Wikipédia"]:::ext
        WS["SearXNG, DuckDuckGo"]:::ext
        RS[("fact_articles<br/>busca vetorial")]:::store
    end
    EVID --> FONTES
    FONTES --> REL["Filtro de relevância NLI<br/>gazetteer do IBGE<br/>descarta outra cidade ou zona"]:::guard
    REL --> VER["Veredito no Jev<br/>true, false, misleading<br/>neutro vira evidência insuficiente"]:::core
    VER --> CRC["Gate CRC<br/>limiar calibrado"]:::guard
    CRC -- "abaixo do limiar" --> IE["insufficient_evidence"]:::guard
    CRC --> GQ{"Matriz GQ01"}:::core
    BOT --> GQ
    GQ -- "IGNORE ou MONITOR" --> LOG[("decisions")]:::store
    GQ -- "INTERVENE_QUEUED" --> Q["InterventionQueue"]:::core
    Q --> LOG
```

Esta é a visão de blocos; as regras de cada etapa estão em [O Pipeline do Agente](pipeline.md). O que importa para o
mapa: **tudo termina em `decisions`**, e só `INTERVENE_QUEUED` segue para a saída.

---

## 6. Rodada de intervenção

A fila vive em memória e publica **no máximo um candidato por rodada** (`INTERVENTION_ROUND_MINUTES`, 15 min), nunca
entre 0 h e 7 h (Brasília).

```mermaid
flowchart TD
    classDef core fill:#2563eb,stroke:#1e3a8a,color:#fff
    classDef guard fill:#d97706,stroke:#78350f,color:#fff
    classDef store fill:#7c3aed,stroke:#4c1d95,color:#fff
    classDef out fill:#16a34a,stroke:#14532d,color:#fff
    classDef ext fill:#475569,stroke:#1e293b,color:#fff

    R(["Rodada vence<br/>a cada 15 min"]):::core --> QH{"Horário de silêncio<br/>0 h às 7 h?"}:::guard
    QH -- "sim" --> M0["Todos viram MONITOR"]:::store
    QH -- "não" --> SORT["Ordena por confiança<br/>do veredito"]:::core
    SORT --> NEXT{"Próximo candidato"}:::core
    NEXT --> T1{"Travas do InterventionService<br/>confiança 0,8 ou mais<br/>não é o próprio bot nem bot<br/>1 quote por post e por autor em 24 h<br/>teto diário e pontos de escrita<br/>postgate permite citação"}:::guard
    T1 -- "barrado" --> NEXT
    T1 -- "passou" --> SRC["Revisão das fontes<br/>5 mais relevantes<br/>e leitura da matéria"]:::core
    SRC --> LLM["LLM redige o quote<br/>pergunta socrática"]:::ext
    LLM --> CRIT{"Critic semântico<br/>a pergunta faz sentido com<br/>o POST, não só com a reportagem?"}:::guard
    CRIT -- "veta" --> NEXT
    CRIT -- "aprova" --> DRY{"INTERVENTION_DRY_RUN?"}:::guard
    DRY -- "sim" --> SIM["Simula, nada publicado"]:::guard
    DRY -- "não" --> PUB["Publica o quote post<br/>até 300 graphemes, em fio se preciso"]:::out
    PUB --> IL[("intervention_logs")]:::store
    PUB --> LAB["Pede o rótulo<br/>possivel-desinformacao"]:::out
    PUB --> REST["Demais candidatos viram MONITOR<br/>preterido por outro mais confiante"]:::store
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
flowchart LR
    classDef ext fill:#475569,stroke:#1e293b,color:#fff
    classDef core fill:#2563eb,stroke:#1e3a8a,color:#fff
    classDef store fill:#7c3aed,stroke:#4c1d95,color:#fff
    classDef guard fill:#d97706,stroke:#78350f,color:#fff
    classDef out fill:#16a34a,stroke:#14532d,color:#fff
    classDef human fill:#db2777,stroke:#831843,color:#fff

    subgraph GAT["Gatilhos (só com PIPELINE_LABELER_ENABLED)"]
        direction TB
        G1["G1. Quote publicado<br/>post: possivel-desinformacao"]:::core
        G2["G2. Bot score alto<br/>conta: provavel-bot<br/>score 0,9 ou mais e 20 posts<br/>nega abaixo de 0,8 (histerese)"]:::core
        G3["G3. Revisão humana reverter<br/>nega possivel-desinformacao"]:::human
    end

    OB["LabelOutbox<br/>registro e repetição"]:::guard
    G1 --> OB
    G2 -->|"estado em account_assessments<br/>muda só após sucesso"| OZC
    G3 -->|"síncrono, erro vai ao revisor"| OZC
    OB --> OZC["OzoneClient<br/>login como contraria-labeler"]:::core
    OB --> LE[("label_events")]:::store

    OZC -->|"emitEvent via proxy atproto_labeler"| PDSL["PDS do labeler"]:::ext
    PDSL -->|"encaminha ao serviço declarado no DID"| TUN["Cloudflare e túnel<br/>contraria.schmidt.monster"]:::guard
    TUN --> GW["gateway Nginx"]:::guard --> OZ["Ozone :3000"]:::out
    OZ --> ODB[("ozone-db")]:::store
    OZD["ozone-daemon"]:::out --> ODB
    OZ --> SIGN["Assina o rótulo<br/>chave atproto_label"]:::out

    SIGN --> APPV["AppView e App Bluesky"]:::ext
    USER(("Quem assina o labeler")):::human --> APPV
    APPV --> VIEW["Aviso informativo<br/>sem borrar o conteúdo"]:::out

    REP(("Denúncia de usuário")):::human -.->|"fila nativa do Ozone<br/>o pipeline não consome"| OZ
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
flowchart LR
    classDef core fill:#2563eb,stroke:#1e3a8a,color:#fff
    classDef store fill:#7c3aed,stroke:#4c1d95,color:#fff
    classDef guard fill:#d97706,stroke:#78350f,color:#fff
    classDef human fill:#db2777,stroke:#831843,color:#fff
    classDef out fill:#16a34a,stroke:#14532d,color:#fff

    WK["worker"]:::core -->|"DatabaseLogHandler<br/>em lotes"| SL[("system_logs")]:::store
    AP["api"]:::core -->|"DatabaseLogHandler"| SL
    DK["docker logs<br/>antigos"]:::guard -->|"backfill_logs"| SL

    OPS(("Operador")):::human -->|"X-Admin-Api-Key"| ADM["API admin<br/>somente-leitura"]:::guard
    ADM --> OV["GET /admin/overview<br/>posts, decisões, intervenções,<br/>LLM, bots, labels, ozone"]:::core
    ADM --> LG["GET /admin/logs"]:::core
    ADM --> TB["GET /admin/db/tables"]:::core
    ADM --> Q["POST /admin/db/query<br/>SELECT e WITH"]:::core
    OV --> LE[("label_events")]:::store
    OV --> OZH["Health público do Ozone<br/>OZONE_HEALTH_URL"]:::out
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
