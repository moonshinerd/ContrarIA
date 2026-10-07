# 0021 — Resiliência das fontes de evidência

- **Status:** Aceita
- **Data:** 05/10/2026
- **Requisitos / GQs:** RNF01, RNF05, RF11

## Contexto
O ContrarIA consulta várias fontes de evidência justamente para continuar funcionando quando uma delas está instável.
Em 05/10/2026 o DuckDuckGo ficou inacessível na rede do servidor de desenvolvimento e a análise desacelerou, o que
mostrou dois defeitos na camada de busca (`app/clients/evidence/web_search.py`):

1. **Lock global durante a chamada de rede.** `CachedSource.search` segurava um lock por fonte enquanto esperava a
   resposta. Com várias análises simultâneas ([ADR 0018](0018-concorrencia-e-contrapressao-do-worker.md)), todas as
   consultas à mesma fonte ficavam na fila atrás de uma que estava travada.
2. **Sem memória de falha.** Cada alegação voltava a tentar a fonte fora do ar e esperava o prazo inteiro (`evidence_timeout_seconds`,
   20 s), por consulta. O `SearXNG` tinha uma espera fixa de 10 s; as demais não tinham nenhuma.

As fontes já eram consultadas em paralelo, cada uma com timeout, e o erro de uma não derrubava as outras. O problema era o
custo de cada falha e a fila atrás do lock.

## Decisão
1. **Chamada única por consulta, sem lock global.** Consultas iguais e simultâneas compartilham uma só chamada (`asyncio.shield`,
   para que o prazo de quem chamou não cancele a dos outros), e consultas diferentes correm em paralelo.
2. **Disjuntor por fonte.** Depois de uma falha, a fonte fica fora por `EVIDENCE_FAILURE_COOLDOWN_SECONDS` (30 s), dobrando a
   cada falha seguida até `EVIDENCE_FAILURE_COOLDOWN_MAX_SECONDS` (600 s). Em espera, ela responde vazio na hora e o
   chamador segue com as outras fontes. Um sucesso zera a contagem. Isso substitui a espera fixa do SearXNG.
3. **Prazo por provedor** no `web_search`: `EVIDENCE_PROVIDER_TIMEOUT_SECONDS` (8 s) para SearXNG e DuckDuckGo. Se estoura, o
   próximo assume e o provedor entra em espera.

## Alternativas consideradas
- **Manter só o timeout geral de 20 s:** cada alegação continuaria pagando esse prazo enquanto a fonte estivesse fora.
- **Desabilitar a fonte pelo resto da sessão** (como foi feito com o Tavily em quota esgotada): fonte instável por rede
  volta sozinha, e o disjuntor a reativa sem reiniciar o worker.

## Consequências
- Fonte instável custa uma falha por janela de espera, não uma por alegação, e não segura as consultas dos outros.
- O DuckDuckGo roda em uma thread (`asyncio.to_thread`) que não pode ser cancelada: depois do prazo, a chamada continua
  até o timeout da biblioteca e só então termina. O disjuntor limita quantas threads se acumulam.
- Os testes cobrem a espera crescente, a ausência de fila atrás de uma consulta lenta e a passagem de vez ao próximo provedor.
- **Não foi medido o ganho de ponta a ponta:** a comparação em escala reduzida foi interrompida antes de terminar. O Google Fact
  Check, a Wikipédia e o acervo RSS têm clientes próprios e não passam por esse disjuntor.
