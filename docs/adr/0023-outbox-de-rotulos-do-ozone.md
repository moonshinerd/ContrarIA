# 0023 — Outbox de rótulos do Ozone

- **Status:** Aceita (complementa o [ADR 0003](0003-labeler-ozone.md) e o [ADR 0017](0017-rotulagem-de-contas-ao-vivo.md))
- **Data:** 07/10/2026
- **Requisitos / GQs:** RF06, RF07, RNF05, RNF06

## Contexto
O rótulo `possivel-desinformacao` é pedido depois de o quote post sair. O Ozone fica atrás de um túnel que depende de
outra máquina ([ADR 0020](0020-acesso-vm-tunel-cloudflare.md)); quando ele cai, a chamada volta 502. O código apenas
registrava a falha em log, então os quotes de 06/10 ficaram sem rótulo e sem registro de que o rótulo falhou.

## Decisão
Cada pedido de rótulo de post vira uma linha em `label_events` (migration `0003_create_label_events`) e é entregue
pelo `LabelOutbox` (`app/services/label_outbox.py`):

- `emit` grava o pedido como `pending` e tenta enviar na hora. Um pedido pendente igual (mesmo alvo, rótulo e ação) é
  reaproveitado.
- Se o Ozone falha, guarda `attempts`, `last_error` e `next_attempt_at` com espera dobrando de
  `LABEL_RETRY_INTERVAL_SECONDS` (60 s) até 1 h. O worker chama `flush` nesse ritmo.
- Após `LABEL_RETRY_MAX_ATTEMPTS` (8) falhas o evento vira `failed` e deixa de ser repetido.
- `/admin/overview` expõe a contagem por estado, o último erro e o health público do Ozone (`OZONE_HEALTH_URL`).

O rótulo `provavel-bot` em contas continua com a lógica própria do ADR 0017 (o estado da conta só muda após o
sucesso e a análise seguinte tenta de novo). A negação por revisão humana segue síncrona, para o erro chegar ao revisor.

## Alternativas consideradas
- **Rotular antes de publicar o quote:** criaria rótulo sem quote se a publicação falhasse.
- **Repetir só em memória:** perdido a cada reinício do worker.
- **Fila externa (Redis, broker):** infraestrutura a mais para um volume de poucas dezenas de rótulos por dia.

## Consequências
- Quedas do túnel deixam de perder rótulos; ficam visíveis e auditáveis.
- Se o worker cair entre publicar o quote e gravar o pedido, o rótulo ainda se perde (janela pequena).
- Um evento `failed` não volta sozinho: exige reenvio manual depois de religar o túnel.
