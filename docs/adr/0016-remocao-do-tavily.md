# 0016 — Remoção do Tavily da busca web

- **Status:** Aceita (ajusta o [ADR 0014](0014-busca-web-searxng-trafilatura.md))
- **Data:** 05/10/2026
- **Requisitos / GQs:** RF11, RNF02, RNF05

## Contexto
O Tavily entrou no MVP como provedor gerenciado de busca web (Issue #21), segundo na cascata
`SearXNG → Tavily → DuckDuckGo` definida no ADR 0014. Ele foi útil para a primeira versão da verificação e aparece
nos experimentos do MVP: o benchmark de fontes (cenários `only_tavily` e `without_tavily`) e o dataset de calibração
CRC foram gerados com ele habilitado.

Com o SearXNG self-hosted em operação, o Tavily passou a ser redundante:

- O SearXNG é gratuito, sem cota, e na avaliação da equipe entrega resultados melhores para notícias em português.
- O Tavily tinha limites de créditos e devolvia erros de quota (HTTP 429, 432 e 433) em operação contínua. O código
  precisou de um tratamento especial para desligá-lo pelo resto da sessão (commit `475eb0e`), e a configuração
  `TAVILY_COOLDOWN_SECONDS` ficou sem uso.
- Manter um provedor pago opcional exige guardar mais uma chave de API e mais um caminho de erro para testar.

## Decisão
**Remover o Tavily do código.** A busca web passa a ser `SearXNG → DuckDuckGo`:

- Saem a classe `TavilyClient`, o registro `tavily` em `EVIDENCE_SOURCES` e as variáveis `TAVILY_API_KEY`,
  `TAVILY_ENABLED` e `TAVILY_COOLDOWN_SECONDS`.
- `WebSearchSource` deixa de receber o parâmetro `tavily`; o DuckDuckGo continua como último recurso sem chave.
- Os testes de cota do Tavily foram trocados por testes de queda do SearXNG com fallback para o DuckDuckGo.
- As configurações do benchmark (`research/benchmarks/verdict/config/*.yaml`) deixam de listar `tavily` entre as fontes.

O que **não** muda: os resultados já publicados continuam válidos como registro do que foi medido na época, e as
tabelas e planilhas de `research/` mantêm a coluna `tavily`. Quem for reproduzir um benchmark antigo precisa
recuperar o commit anterior a esta decisão.

## Alternativas consideradas
- **Manter o Tavily desabilitado por flag:** deixaria código e chave sem uso, e a flag já estava em `false` na operação.
- **Aplicar cooldown também aos erros 401 e 5xx do Tavily:** só melhoraria um provedor que deixou de ser necessário.
- **Trocar por outro provedor pago (Serper, SerpAPI):** já rejeitado no ADR 0014 por custo e risco de interrupção.

## Consequências
- Há uma credencial a menos para gerenciar e um caminho de falha a menos.
- A qualidade da busca web passa a depender do SearXNG e dos motores que ele agrega. Se ele cair, o DuckDuckGo
  assume com resultados mais ruidosos.
- **Os benchmarks de verdict e a calibração CRC do Jev não foram refeitos sem o Tavily.** O efeito da remoção sobre
  essas métricas não foi medido; vale reexecutar a calibração antes de confiar nos limiares publicados para o
  conjunto de fontes atual.
- Ambientes com `TAVILY_*` no `.env` continuam funcionando: as variáveis são ignoradas (`extra="ignore"`).
