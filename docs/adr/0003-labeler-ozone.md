# 0003 — Uso do Servidor Oficial Ozone para Rotulagem Descentralizada

- **Status:** Aceita
- **Data:** 16/09/2026
- **Requisitos / GQs:** RF07, RNF03, RNF07, GQ07
- **Origem:** [Issue #16](https://github.com/moonshinerd/ContrarIA/issues/16)

## Contexto
O MVP precisa emitir e remover rótulos após a análise completa, com rastreabilidade. A biblioteca leve `@skyware/labeler` foi descartada porque estava arquivada, conforme registrado na issue #16. Ozone é o servidor oficial de moderação do Bluesky, distinto dessa biblioteca.

## Decisão
Manter uma instância do **Ozone oficial** no MVP, com uma **segunda conta Bluesky dedicada ao labeler**, separada da conta que publica quote posts. O serviço ficará atrás do Caddy, com HTTPS, Postgres próprio, chave de assinatura e serviço `#atproto_labeler` configurados no DID.

Declarar no record `app.bsky.labeler.service` os rótulos `possivel-desinformacao` e `provavel-bot`; `evidencia-insuficiente` é opcional. As definições usam locale `pt-BR`, `severity: inform` e `blurs: none`. Os usuários escolhem assinar o labeler para visualizar sua sinalização.

O pipeline aplica rótulos somente após a análise completa, em posts ou contas conforme a decisão. Usa `tools.ozone.moderation.emitEvent` com `createLabelVals` e nega rótulos com `negateLabelVals` quando um veredito é revisto, preservando o histórico. Abstenção não autoriza ação penalizadora.

## Alternativas consideradas
- **`@skyware/labeler`:** descartada por arquivamento, evitando depender de uma implementação sem manutenção.
- **Rótulos apenas no banco interno:** não alcançam os clientes da rede.
- **Avisos apenas em texto:** não oferecem as preferências de moderação nativas dos clientes.

## Consequências
- A sinalização é distribuída pelo AT Protocol e pode ser revogada sem apagar o histórico.
- A conta do labeler deve ser assinada pelo usuário; publicar rótulos não os torna visíveis para toda a rede.
- A equipe mantém um serviço público adicional, sua conta, banco, chave de assinatura e certificados.
