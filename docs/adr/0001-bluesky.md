# 0001 — Adoção da Plataforma Bluesky (AT Protocol) em vez de X ou Instagram

- **Status:** Aceita
- **Data:** 16/09/2026
- **Requisitos / GQs:** RF01, RF07, RNF03, RNF07, GQ05

## Contexto
O projeto ContrarIA tem como objetivo combater a desinformação política por meio de intervenções automatizadas e sinalização técnica. Para viabilizar a solução, era necessário selecionar uma rede social pública que permitisse:
1. Coleta contínua de publicações com baixa latência e sem custos proibitivos.
2. Capacidade de realizar intervenções públicas e auditar contas de terceiros.
3. Mecanismos transparentes e descentralizados de moderação de conteúdo.

As redes sociais comerciais dominantes (X/antigo Twitter e Instagram/Meta) impuseram barreiras severas nos últimos anos: o X elevou o plano de API básico para valores inacessíveis a projetos acadêmicos (US$ 100/mês para quotas mínimas) e mantém políticas agressivas de banimento de contas automatizadas; o Instagram não oferece API aberta para escuta de feeds públicos em tempo real.

## Decisão
Adotar exclusivamente a rede social **Bluesky**, construída sobre o protocolo descentralizado e de código aberto **AT Protocol** (Authenticated Transfer Protocol). O sistema utilizará a API oficial pública e o *firehose* em tempo real **Jetstream**.

## Alternativas consideradas
- **X / Twitter**: Descartado devido aos custos inviáveis de acesso à API, restrições contratuais para pesquisa e instabilidade nas regras de desenvolvedores.
- **Instagram / Meta**: Descartado pela ausência de APIs de leitura contínua de publicações abertas e restrição estrita a contas corporativas fechadas.
- **Mastodon / ActivityPub**: Descartado por possuir uma base de usuários política menos centralizada no Brasil e menor maturidade de ferramentas unificadas de moderação como o Ozone.

## Consequências
- **Positivas**:
  - Acesso gratuito, irrestrito e de baixíssima latência ao fluxo global de mensagens via *Jetstream*.
  - Suporte nativo e documentado a provedores de moderação independentes (*Labelers* via Ozone).
  - Ecossistema alinhado aos princípios de transparência e auditoria pública de algoritmos.
- **Negativas / Riscos assumidos**:
  - A base total de usuários no Bluesky, embora em rápido crescimento no Brasil, é menor que a do X.
  - O AT Protocol é um ecossistema em evolução, demandando atenção a possíveis atualizações nos esquemas Lexicon da API.
