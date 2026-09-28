# 0009 — Coleta Híbrida de Publicações via Jetstream e API searchPosts

- **Status:** Aceita
- **Data:** 16/09/2026
- **Requisitos / GQs:** RF01, RF08, RNF07, GQ04, GQ05, Issue #11

## Contexto
O ecossistema do AT Protocol (Bluesky) disponibiliza duas formas principais de acesso a conteúdos públicos:
1. **Jetstream (WebSocket Stream)**: Transmite eventos de criação de registros (`app.bsky.feed.post`) na rede em tempo real, com altíssima vazão e sem latência.
2. **searchPosts (REST Polling)**: Endpoint HTTP de busca textual que retorna postagens já indexadas pela plataforma, permitindo filtrar por termos de consulta, contagem de curtidas e alcance.

Se o sistema utilizar apenas o *Jetstream*, recebe uma enxurrada de publicações instantâneas, mas sem saber de antemão quais delas se tornarão virais ou terão grande alcance. Se utilizar apenas o *searchPosts*, sofre com limites de requisições por minuto da API e atraso temporal na detecção de conteúdos recém-lançados.

## Decisão
Implementar uma arquitetura de **coleta híbrida**:
1. **Escuta Contínua via Jetstream**: Um worker em segundo plano mantém uma conexão WebSocket persistente com o Jetstream, filtrando postagens em português por termos-chave políticos para alimentar o histórico de atividade de contas e detecção precoce de anomalias (RF01/RF12).
2. **Varredura Periódica via searchPosts**: Tarefas agendadas realizam consultas a cada poucos minutos com ordenação por engajamento recente, capturando publicações com rápida aceleração de compartilhamentos que mereçam intervenção prioritária (RF04/RF08).

## Alternativas consideradas
- **Coleta Exclusiva por Polling REST**: Descartada devido ao risco de bloqueio por taxa de requisições (*rate limit*) e perda da visão global de comportamento em tempo real das contas.
- **Coleta Exclusiva por Jetstream**: Descartada pela complexidade e custo de manter um banco de dados gigantesco para rastrear a evolução de métricas de curtidas de milhões de posts no MVP.

## Consequências
- **Positivas**:
  - Melhor equilíbrio entre velocidade de descoberta (tempo real) e relevância de impacto (viralidade consolidada).
  - Resiliência: caso o WebSocket sofra desconexões temporárias, as buscas REST cobrem o intervalo.
  - Alinhamento pleno com os requisitos RF01 e RNF07.
- **Negativas / Riscos assumidos**:
  - Necessidade de deduplicação de mensagens no banco de dados para evitar reprocessar posts que cheguem pelas duas vias.
