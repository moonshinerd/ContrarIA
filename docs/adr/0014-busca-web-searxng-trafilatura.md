# 0014 — Busca Web Self-Hosted com SearXNG e Extração via Trafilatura

- **Status:** Aceita (a cascata foi simplificada pelo [ADR 0016](0016-remocao-do-tavily.md), que removeu o Tavily)
- **Data:** 30/09/2026
- **Requisitos / GQs:** RF11, RNF02, RNF05
- **Origem:** Branch `feature/crc-calibracao-automatica`

## Contexto

A verificação factual em tempo real exige recuperar rapidamente fontes jornalísticas primárias sobre eventos recentes no Brasil. O pipeline dependia de provedores comerciais gerenciados (Tavily) e raspagem direta (DuckDuckGo). No entanto:
1. O Tavily impõe limites estritos de créditos gratuitos e retorna erro de quota (HTTP 432) em operação contínua, paralisando a recuperação caso não haja créditos faturados.
2. O DuckDuckGo HTML simples é sujeito a *rate limits* e oferece cobertura reduzida de veículos regionais e portais especializados em tempo real.
3. A raspagem pura com BeautifulSoup para recuperar o corpo das reportagens frequentemente captura poluição de DOM (menus, anúncios, cabeçalhos, rodapés), degradando o contexto fornecido ao modelo Jev.

## Decisão

1. **Metabuscador Self-Hosted (SearXNG):** Adotar o SearXNG em contêiner Docker oficial integrado ao `docker-compose.yml` e `deploy/docker-compose.prod.yml`. O serviço expõe internamente sua API JSON (porta 8080) configurada para o idioma `pt-BR` e categorias prioritárias (`news` e `general`), agregando motores globais e regionais com latência baixa (~1,2s) e consumo enxuto (~160 MiB de RAM).
2. **Cascata Resiliente de Busca:** No adaptador `WebSearchSource`, priorizar o SearXNG local como mecanismo primário. Caso indisponível, chavear automaticamente para Tavily e DuckDuckGo, tratando expressamente erros de quota (432) do Tavily para evitar repetições desnecessárias.
3. **Extração de Texto Principal com Trafilatura:** Adotar a biblioteca `trafilatura` no extrator de artigos (`ArticleExtractor`), mantendo BeautifulSoup apenas como fallback. O Trafilatura remove boilerplate de HTML, menus e scripts, entregando somente o conteúdo editorial limpo.
4. **Build e Deploy Automatizados:** Integrar as configurações (`searxng/settings.yml`) e a imagem oficial diretamente no ciclo de vida do Docker Compose, sem etapas manuais para subida local ou em produção.

## Alternativas consideradas

- **Provedores Comerciais Pagos (Tavily Pro / Serper / SerpAPI):** Rejeitados devido à violação do princípio de custo operacional mínimo e risco de interrupção por faturamento.
- **Mecanismos P2P (YaCy):** Rejeitado por alta latência e indexação irregular de notícias recentes brasileiras.
- **Crawlers com Indexação Própria (Elasticsearch / Meilisearch):** Descartados por demandar infraestrutura de rastreamento contínuo inviável para uma VPS de hardware modesto.

## Consequências

- **Positivas:**
  - Autossuficiência e custo zero para a descoberta de URLs e checagem factual.
  - Imunidade à expiração de planos gratuitos de terceiros.
  - Maior precisão na extração de texto jornalístico, fornecendo evidências mais ricas e sem ruídos ao modelo Jev.
- **Negativas / Riscos assumidos:**
  - Adição de um contêiner adicional (~160 MiB de RAM) na infraestrutura.
  - Caso haja picos anômalos de requisições a partir de um mesmo IP público, motores comerciais consultados pelo SearXNG podem retornar CAPTCHA ou HTTP 429, exigindo manter a cascata com fallback.
