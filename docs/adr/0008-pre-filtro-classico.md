# 0008 — Pré-filtro Clássico Supervisionado em Datasets PT-BR

- **Status:** Aceita
- **Data:** 16/09/2026
- **Requisitos / GQs:** RF09, RNF05, GQ04, Issue #26

## Contexto
O fluxo contínuo de postagens coletadas no Bluesky é volumoso e heterogêneo. Submeter todas as publicações diretamente ao pipeline complexo de LLMs (CoVe + Self-RAG + Debate) esgotaria o orçamento e as cotas diárias de API em minutos, violando o requisito RNF05 (Controle de custos e recursos).
É necessário dispor de uma etapa de triagem de baixíssimo custo computacional que elimine textos inócuos, conversas triviais e postagens sem probabilidade de desinformação antes do acionamento dos modelos generativos.

## Decisão
Treinar e integrar um **classificador clássico de aprendizado de máquina supervisionado** (TF-IDF vetorizado combinado com classificador linear como Regressão Logística ou LightGBM), treinado com *datasets* públicos de desinformação em língua portuguesa (Fake.br-Corpus e FactCheck-BR).
O modelo atua como um portão de descarte (*gatekeeper*): apenas as publicações cujo escore de risco de desinformação ultrapassar um limiar calibrado avançam para a verificação com LLM.

## Alternativas consideradas
- **Pré-filtro com LLM Leve (ex.: GPT-4o-mini / Haiku)**: Descartado porque, mesmo com custo unitário reduzido, o volume massivo de requisições ainda geraria custos expressivos e latência desnecessária de rede.
- **Filtro Estático por Lista de Palavras-Chave (*Regex*)**: Descartado pela alta taxa de falsos negativos e incapacidade de capturar nuances de contexto ou ironia.

## Consequências
- **Positivas**:
  - Inferência em microssegundos no ambiente local da API (CPU comum, sem necessidade de GPU).
  - Redução estimada de 70% a 85% no volume de postagens encaminhadas para as LLMs pagas, protegendo o orçamento do projeto.
  - O pipeline é modular: a presença do pré-filtro é desacoplada e não bloqueia o fluxo principal da integração.
- **Negativas / Riscos assumidos**:
  - Possibilidade de viés temporal decorrente do vocabulário estático dos datasets de treino (necessidade de recalibração periódica com novos dados).
