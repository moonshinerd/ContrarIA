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
4. **Poda inicial:** ao subir, o worker mantém os `teto` pendentes de maior prioridade e marca o resto como `expired`
   (status final; os posts continuam no banco).
5. Tudo isso é configurável para cada máquina; veja o guia de ajuste em [Dados, Infraestrutura e Deploy](../arquitetura/dados-e-infra.md).

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
