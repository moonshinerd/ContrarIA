# 0005 — Cesta Diversificada de Fontes de Evidência com Adapters Desacoplados

- **Status:** Aceita
- **Data:** 16/09/2026
- **Requisitos / GQs:** RF11, RNF02, GQ03, Issues #20, #21

## Contexto
O processo de verificação da verdade factual não pode apoiar-se exclusivamente na base de dados pré-treinada dos modelos de linguagem, que sofre de desatualização temporal (*knowledge cutoff*) e propensão a alucinações. Por outro lado, depender de uma única fonte externa de checagem gera vulnerabilidades críticas:
1. O *Google Fact Check Tools API* indexa apenas alegações que já foram formalmente checadas por agências de notícias jornalísticas, deixando um vácuo temporal para boatos recém-criados.
2. A *Wikipedia* oferece excelente contextualização histórica e biográfica, mas não cobre acontecimentos de última hora.
3. Mecanismos de busca web gerais (DuckDuckGo / Tavily) trazem conteúdo em tempo real, mas podem retornar blogs não verificados ou novos boatos como se fossem evidências.

## Decisão
Projetar uma arquitetura de **múltiplas fontes de evidência** regida pela porta abstrata `EvidenceSource`. O pipeline consulta uma cesta balanceada em dois níveis:
1. **Fontes Curadas Primárias**: Google Fact Check Tools API e Wikipedia API com cache de respostas em memória (Issue #20).
2. **Fontes Dinâmicas em Tempo Real**: Provedor de busca web (DuckDuckGo/Tavily), acervo indexado via pgvector e feeds RSS de agências de checagem nacionais e órgãos oficiais como o TSE (Issue #21).

## Alternativas consideradas
- **Dependência Exclusiva do Google Fact Check**: Descartada pela baixa cobertura de boatos emergentes (*zero-day fake news*).
- **RAG Genérico Apenas com Busca Web**: Descartada pelo risco de capturar desinformação propagada em múltiplos sites de baixa credibilidade como fonte de verdade.

## Consequências
- **Positivas**:
  - Resiliência operacional: se uma API externa estiver instável ou com quota esgotada, as demais fontes continuam operando.
  - Cruzamento de dados para consenso: a convergência entre uma checagem do TSE e um artigo enciclopédico eleva a nota de confiança para o veredito.
  - Conformidade estrita com o requisito RNF02 (Atualidade das informações).
- **Negativas / Riscos assumidos**:
  - Maior latência de rede no pipeline devido à necessidade de consultas paralelas assíncronas a múltiplos serviços externos.
