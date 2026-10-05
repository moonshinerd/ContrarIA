# 0015 — Pré-filtro TF-IDF não integrado ao pipeline

- **Status:** Aceita (substitui o [ADR 0008](0008-pre-filtro-classico.md))
- **Data:** 05/10/2026
- **Requisitos / GQs:** RNF01, RNF05, GQ04

## Contexto
O ADR 0008 propôs um classificador TF-IDF como sinal opcional de priorização, para reduzir chamadas caras de
verificação. O modelo foi treinado e avaliado (`research/experiments/results/evaluation_report.json`), mas **nunca
foi ligado ao worker**: `FakeNewsTFIDFClassifier` só é referenciado por testes e pela pesquisa.

Desde o ADR 0008 o contexto mudou. A verificação deixou de ser um LLM em nuvem cobrado por chamada e passou a ser
local (Jev, [ADR 0013](0013-backend-local-jev.md)), o que elimina o argumento de custo do pré-filtro.

## Evidências
| Cenário | F1 | ROC-AUC |
|---|---|---|
| Regressão logística, notícias completas | 0,965 | 0,992 |
| Regressão logística treinada em notícias, aplicada a texto curto | 0,815 | 0,970 |
| Especialista em texto curto (teste do mesmo dataset) | 0,932 | 0,981 |
| **Amostra anotada de posts do Bluesky** | **0,720** | **0,760** |

A amostra do Bluesky tem acurácia 0,65 e é muito pequena, então esse número é indicativo, não conclusivo. O ponto
central é a mudança de domínio: o modelo aprende o estilo de notícias falsas dos datasets (Fake.br, FakeRecogna), não
a falsidade de uma alegação em um post curto de opinião política.

## Decisão
**Não integrar o TF-IDF ao pipeline.** O código e o modelo permanecem em `research/` e em
`app/models/classifiers/` como baseline reproduzível, mas fora do fluxo do worker.

A função de "não gastar verificação em posts sem o que checar" já é cumprida por uma heurística **determinística**,
sem LLM nem Jev, em `jev_verification.py`:

- `_candidate_sentences` divide o post em frases, remove hashtags de campanha e URLs e limita a 6 candidatas.
- `_is_verifiable_claim` descarta perguntas e expressões idiomáticas e exige um ancoramento factual: número ou ano,
  título político ou institucional, predicado fático ou judicial, sigla institucional ou nome próprio.

O que o Jev faz depois é filtrar a relevância das **evidências** e classificar o veredito por NLI. Ele não decide
se a frase é verificável.

## Alternativas consideradas
- **Integrar o TF-IDF como está:** rejeitado pelo desempenho fora do domínio e pela ausência de ganho de custo.
- **Similaridade com checagens conhecidas:** comparar o post com `fact_articles` (embeddings MiniLM no pgvector)
  como sinal de prioridade na triagem. Os componentes já existem, mas hoje só são usados dentro da verificação. É a
  opção mais promissora, **ainda não implementada nem medida**.
- **Ajuste fino em posts curtos (por exemplo, BERTimbau):** depende de uma amostra anotada do Bluesky maior do que a atual.

## Consequências
- A fila é priorizada só por relevância, velocidade de propagação e bot score. Esses sinais medem alcance, não a
  chance de o post ser falso.
- **O filtro de alegações verificáveis é uma heurística sem validação quantitativa.** A validação de `research/`
  (`claim_extraction_validation.json`, 12 casos) cobre a extração por LLM do backend anterior, não esse filtro.
  Medir precisão e cobertura dele numa amostra anotada é um trabalho pendente.
- O ADR 0008 fica marcado como substituído, mantendo o histórico da decisão original.
