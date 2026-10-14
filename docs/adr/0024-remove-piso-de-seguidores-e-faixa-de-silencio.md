# 0024 — Remoção do piso de seguidores e da faixa de silêncio

- **Status:** Aceita (altera o [ADR 0018](0018-concorrencia-e-contrapressao-do-worker.md) e o [ADR 0022](0022-janela-de-maturacao-e-critic-semantico.md); pode ser revertida a qualquer momento)
- **Data:** 14/10/2026
- **Requisitos / GQs:** RF05, RF06, RNF01, GQ01

## Contexto
Em 12 a 14/10/2026 o worker analisou 700 posts e nenhum virou intervenção. Dois filtros de política de atuação
(não de qualidade) escondiam isso: só autores com `PIPELINE_MIN_FOLLOWERS_FOR_INTERVENTION` (500) seguidores ou mais
chegavam à fila, e a rodada de intervenção não rodava entre 0h e 7h (Brasília). Com eles, até veredictos adversos
terminavam em `MONITOR` ("Condição não coberta pela matriz" e "Horário de silêncio"), o que dificultava medir a
qualidade real do pipeline.

## Decisão
- **Piso de seguidores:** o padrão passa de 500 para **0** (sem barreira). Qualquer autor com veredito `false` ou
  `misleading` entra na fila de intervenção.
- **Faixa de silêncio:** passa a ser opcional por `INTERVENTION_QUIET_HOURS_ENABLED` e fica **desligada** por padrão.
- As demais travas continuam: uma intervenção por rodada de 15 min, `DAILY_MAX_INTERVENTIONS`, orçamento diário de
  LLM, pontos de escrita da API do Bluesky, critic semântico e `INTERVENTION_DRY_RUN`.
- Junto, o veredito adverso passou a exigir fonte independente de peso (checagem, imprensa ou oficial): só Wikipédia ou
  o link do próprio post vira `insufficient_evidence`. Sem essa regra, tirar as barreiras expunha falsos positivos.

## Como reativar
Nenhuma mudança de código; basta ajustar o `.env` do servidor e reiniciar `api` e `worker`:

| Barreira | Variável | Valor para reativar |
|---|---|---|
| Piso de seguidores | `PIPELINE_MIN_FOLLOWERS_FOR_INTERVENTION` | `500` (ou o piso desejado) |
| Faixa de silêncio | `INTERVENTION_QUIET_HOURS_ENABLED` | `true` (janela em `INTERVENTION_QUIET_START_HOUR`/`END_HOUR`, padrão 0 e 7) |

## Consequências
- Mais posts chegam à fila; o volume continua limitado a uma intervenção a cada 15 min e ao teto diário.
- Com piso 0, a regra `IGNORE` (bot score acima de 0,9 **e** conta pequena) deixa de disparar, porque toda conta
  passa a contar como "com alcance suficiente". Contas muito automatizadas não são mais ignoradas por esse critério.
- Se o servidor tiver `PIPELINE_MIN_FOLLOWERS_FOR_INTERVENTION=500` no `.env`, esse valor continua valendo: o padrão
  novo só vale quando a variável não está definida.
- Mantenha `INTERVENTION_DRY_RUN=true` até revisar manualmente alguns casos `INTERVENE`.
