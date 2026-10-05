# 0018 — Análises simultâneas e teto de fila no worker

- **Status:** Aceita
- **Data:** 05/10/2026
- **Requisitos / GQs:** RNF05, RF08, RF10, GQ04

## Contexto
O worker analisava **um post de cada vez**, em lotes de 5 seguidos de uma pausa de 30 s, e media cerca de **1,7 a 2,2
análises por minuto**. Enquanto isso a coleta trazia ~270 posts/min do Jetstream mais ~430 do `searchPosts` a cada
10 min, e a fila de candidatos chegou a **36 mil posts**: a análise escolhia o melhor por prioridade, mas ficava a horas
de distância dos posts frescos, que são os que ainda valem um quote post.

## Medições
Ambiente: 10 CPUs e 16 GB no Docker, worker parado durante os testes, SearXNG local. O script
`python -m app.scripts.benchmark_concurrency` chama só a verificação (Jev), sem gravar decisão nem publicar.

**Verificação isolada, amostra aleatória da fila (20 posts por nível, conjuntos distintos):**

| Simultâneas | Posts/min | Latência p50 | Latência p95 |
|---|---|---|---|
| 1 | 20,3 | 2,9 s | 7,0 s |
| **3** | **33,1** | 6,0 s | 8,2 s |
| 6 | 18,5 | 9,6 s | 39,7 s |
| 10 | 19,2 | 12,2 s | 47,4 s |

**Verificação isolada, os posts de maior prioridade (os que o worker realmente pega; 12 por nível):**

| Simultâneas | Posts/min | Latência p50 | Latência p95 |
|---|---|---|---|
| 1 | 9,7 | 5,8 s | 12,2 s |
| **3** | **13,4** | 9,5 s | 20,9 s |
| 5 | 9,3 | 16,3 s | 41,0 s |

Acima de 3 a vazão **cai** e a cauda de latência explode: o serviço `jev` chegou a 687% de CPU (de 1000%), então
mais simultâneas só disputam os mesmos núcleos. As demais etapas da análise (perfil, bot score, contexto do fio) somam
cerca de 1 s por post.

**De ponta a ponta, worker novo (3 simultâneas, fila de 100), 10 minutos:** **90 análises, 9,4 por minuto**, contra 1,7 a
2,2 antes (cerca de 4 a 5 vezes), sem falhas.

## Decisão
1. **Pool de análises simultâneas** (`AnalysisPool`), configurável por `WORKER_PIPELINE_CONCURRENCY` (padrão **3**).
   Não há mais lote fixo nem pausa ociosa: uma vaga que libera é preenchida na hora com o próximo da fila.
   Um post que falha `WORKER_PIPELINE_MAX_ATTEMPTS` vezes (padrão 3) sai da fila como `ignored`, para não ocupar vaga.
2. **Teto de fila** `WORKER_QUEUE_MAX_PENDING` (padrão **100**; `0` desliga). Cheia a fila, a coleta **descarta** os posts
   novos (o cursor do Jetstream continua andando), de modo que a análise só vê posts frescos.
3. **Reserva para o `searchPosts`** `WORKER_QUEUE_SEARCH_RESERVE` (padrão **30**): o Jetstream só preenche até
   `teto − reserva`. Sem ela, o firehose enchia a fila antes do ciclo do poller, que inseriu 1 de 431 posts na primeira
   medição ao vivo.
   O `searchPosts` devolve a cada ciclo quase os mesmos posts populares das últimas 24 h; por isso só os URIs ainda
   desconhecidos contam como novos e ocupam vaga (o `upsert` já ignorava duplicados, mas o log e a reserva os contavam).
4. **Poda inicial:** ao subir, o worker mantém os `teto` pendentes de maior prioridade e marca o resto como `expired`
   (status final; os posts continuam no banco).
5. Tudo isso é configurável para cada máquina; veja o guia de ajuste em [Dados, Infraestrutura e Deploy](../arquitetura/dados-e-infra.md).

## Medição na VM de produção

Ambiente: VM Debian 12 com **4 vCPU, 9,7 GB de RAM e 40 GB de disco**, sem GPU, rodando a pilha completa (db, jev,
searxng, Ozone). Mesmo script (`benchmark_concurrency`), 20 posts por nível amostrados de uma coleta do Jetstream
(116 posts de 73 autores, ~160 caracteres em média), Jev chamado por HTTP como em produção.

| Simultâneas | Posts/min VM | p50 VM | p95 VM | | Posts/min Mac | p50 Mac | p95 Mac |
|---|---|---|---|---|---|---|---|
| 1 | **4,7** | **14,2 s** | **29,1 s** | | 20,3 | 2,9 s | 7,0 s |
| 2 | 4,4 | 21,7 s | 54,0 s | | n/d | n/d | n/d |

- **A VM é ~5× mais lenta que o Mac** (vazão de 4,7 contra 20,3 posts/min com 1 simultânea) e **não atinge a meta de
  10 s** por post (p95 de 29 s). Sem erros em nenhum nível medido.
- **O gargalo é a CPU do Jev.** Durante a análise o container `jev` usa ~360% dos 400% disponíveis; a RAM sobra
  (`jev` ~0,7 GB, máquina inteira ~2,3 GB de 9,7 GB). O modelo é único e a inferência passa por um lock
  (`_infer_lock` em `models/classifiers/jev.py`), então **mais simultâneas não aumentam a vazão**: só sobrepõem a busca
  de evidência e alongam a latência de cada post.
- **Decisão para a VM: `WORKER_PIPELINE_CONCURRENCY=1`.** O padrão do código continua 3 (calibrado no Mac).
- O `worker` com o modelo de embeddings do pré-filtro chegou a ~90% do limite de 1 GB; o compose de produção passou
  a 2 GB.
- **Fila na VM:** `WORKER_QUEUE_MAX_PENDING=100` e `WORKER_QUEUE_SEARCH_RESERVE=70`. A fila **não troca posts piores
  por melhores**: com ela cheia, posts novos são descartados. Ela se renova à medida que os posts são analisados
  (~47 vagas por ciclo de 10 min nessa vazão). Com a reserva alta, o Jetstream ocupa no máximo 30 vagas (posts recém
  publicados, ainda sem engajamento) e as outras 70 ficam para o `searchPosts` ordenado por `top`, que traz os posts
  de maior alcance. No primeiro ciclo ao vivo o poller inseriu 70 posts novos de 435 encontrados.
- **Limites desta medição:** amostra de 20 posts por nível; os níveis 3, 4 e 6 não foram medidos (interrompi o
  benchmark depois de ver que a vazão não cresce com a concorrência); uma única máquina. Todos os 20 posts do nível 1
  saíram como `insufficient_evidence`, o esperado para posts coletados sem filtro de tema, mas a latência de posts com
  mais evidência (mais pares NLI) pode ser maior. Uma medição do custo do NLI por par foi descartada: rodou com o
  servidor ainda processando requisições do benchmark interrompido.
- **Caminhos para reduzir a latência, se for preciso** (todos alteram a calibração CRC e exigem recalibrar):
  limitar a quantidade de pares NLI por post, reduzir `max_length` do tokenizador ou quantizar o modelo. A outra saída
  é uma máquina com mais núcleos.

## Alternativas consideradas
- **Pausar a leitura e retomar do cursor:** não perde nada, mas a análise passaria a pegar posts de horas atrás.
- **Concorrência alta (6 a 10):** a medição mostrou queda de vazão e latência de cauda muito pior.
- **Não limitar a fila:** mantém a seleção por prioridade sobre todo o fluxo, ao custo de uma fila que só cresce.

## Consequências
- **A seleção por prioridade fica mais estreita.** Antes o worker escolhia o melhor entre dezenas de milhares de posts;
  agora escolhe entre os ~100 que estavam na fila quando havia vaga. A reserva do `searchPosts` atenua isso, mas não
  elimina: os posts de grande alcance que chegam com a fila cheia pelo Jetstream são perdidos. A conta precisa de
  1.000 seguidores ou mais para receber quote, então esse efeito deve ser acompanhado.
- A vazão passa a depender do `jev`: uma máquina com menos núcleos satura com menos simultâneas.
- **Limites das medições:** amostras pequenas (12 a 20 posts por nível), conjuntos de posts diferentes entre níveis e
  uma única máquina. O ganho de ponta a ponta mistura dois efeitos que não separei: a concorrência e a remoção da pausa
  de 30 s entre lotes. A medição ao vivo cobre só a concorrência 3.
- Os limites de API continuam valendo: o Google Fact Check tem o limitador de 240 requisições/min e o SearXNG local não
  tem cota própria, mas depende dos motores que ele agrega, que podem limitar o IP.
